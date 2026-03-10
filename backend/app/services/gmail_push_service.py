"""
Gmail Push Service — near-real-time email trigger for agents.

Polls IMAP INBOX on a short interval.  When a brand-new unseen email
arrives (UID > last known UID), the agent's trigger fires with the
email context prepended to the trigger prompt.

Design notes:
  • Reuses the existing IMAP credentials stored in user_service.
  • Runs an asyncio background loop similar to TriggerScheduler.
  • Maintains a per-agent "last_seen_uid" in the trigger sub-document
    so duplicate firings never happen, even across restarts.
"""

import asyncio
import imaplib
import email as email_lib
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Any

from app.tools.email_encryption import decrypt

logger = logging.getLogger(__name__)

POLL_SECONDS = 30  # check every 30 seconds


class GmailPushService:
    """Background service that watches Gmail for new emails and fires agent triggers."""

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="gmail-push")

    # ── lifecycle ────────────────────────────────────────────────

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Gmail push service started (poll every %ds)", POLL_SECONDS)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._executor.shutdown(wait=False)
        logger.info("Gmail push service stopped")

    # ── main loop ────────────────────────────────────────────────

    async def _loop(self):
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Gmail push tick error: %s", e, exc_info=True)
            await asyncio.sleep(POLL_SECONDS)

    async def _tick(self):
        from app.services.agent_store import agent_store
        from app.services.agent_service import agent_service

        if not agent_store.is_ready or not agent_service.is_ready:
            return

        agents = self._get_gmail_push_agents(agent_store)
        if not agents:
            return

        loop = asyncio.get_running_loop()
        for agent_doc in agents:
            try:
                await loop.run_in_executor(
                    self._executor,
                    self._check_and_fire,
                    agent_doc,
                )
            except Exception as e:
                logger.error(
                    "Gmail push error for agent %s: %s",
                    agent_doc.get("id"),
                    e,
                    exc_info=True,
                )

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _get_gmail_push_agents(agent_store) -> list[dict]:
        """Return agents with active gmail_push triggers."""
        agents = agent_store.list_agents()
        result = []
        for agent in agents:
            trigger = agent.get("trigger")
            if (
                trigger
                and trigger.get("type") == "gmail_push"
                and trigger.get("active", False)
            ):
                result.append(agent)
        return result

    @staticmethod
    def _check_and_fire(agent_doc: dict):
        """
        Connect to IMAP, look for new emails since last_seen_uid,
        and fire the agent for each new email found.
        """
        from app.services.agent_store import agent_store
        from app.services.agent_service import agent_service
        from app.services.user_service import user_service

        agent_id = agent_doc["id"]
        trigger = agent_doc["trigger"]
        prompt = trigger.get("prompt", "")
        filter_from = trigger.get("filter_from", "")
        filter_subject = trigger.get("filter_subject", "")
        filter_body = trigger.get("filter_body", "")
        filter_header = trigger.get("filter_header", "")
        max_age_minutes = trigger.get("max_age_minutes", 0)
        filter_after_date = trigger.get("filter_after_date", "")
        last_seen_uid = trigger.get("last_seen_uid", 0)

        # CRITICAL: If no explicit filter_after_date, default to the
        # trigger's created_at timestamp.  A trigger should NEVER process
        # emails from before it was created.
        if not filter_after_date:
            created_at = trigger.get("created_at", "")
            if created_at:
                try:
                    # created_at is ISO 8601 — take only the date portion
                    filter_after_date = created_at[:10]  # "YYYY-MM-DD"
                    logger.info(
                        "Agent %s: no filter_after_date set, defaulting to trigger created_at: %s",
                        agent_id, filter_after_date,
                    )
                except Exception:
                    pass

        # Get email credentials
        account = user_service.get_email_account("1")
        if not account:
            logger.debug("Agent %s: no email account configured — skipping gmail push", agent_id)
            return

        imap_host = account.get("imap_host")
        imap_port = account.get("imap_port", 993)
        if not imap_host:
            logger.debug("Agent %s: no IMAP host configured — skipping gmail push", agent_id)
            return

        try:
            password = decrypt(account["password_encrypted"])
        except Exception as e:
            logger.error("Agent %s: failed to decrypt email password: %s", agent_id, e)
            return

        # Connect to IMAP
        try:
            conn = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=30)
            conn.login(account["username"], password)
            conn.select("INBOX")
        except Exception as e:
            logger.error("Agent %s: IMAP connect failed: %s", agent_id, e)
            return

        try:
            new_emails = _fetch_new_emails(
                conn,
                last_seen_uid=last_seen_uid,
                filter_from=filter_from,
                filter_subject=filter_subject,
                filter_body=filter_body,
                filter_header=filter_header,
                max_age_minutes=max_age_minutes,
                filter_after_date=filter_after_date,
            )
        except Exception as e:
            logger.error("Agent %s: IMAP fetch error: %s", agent_id, e)
            conn.logout()
            return

        if not new_emails:
            conn.logout()
            return

        logger.info(
            "Agent %s: %d new email(s) detected (UIDs: %s)",
            agent_id,
            len(new_emails),
            [e["uid"] for e in new_emails],
        )

        # Fire the agent for each new email
        foundry_agent_id = agent_doc.get("foundry_agent_id", "")
        thread_id = agent_doc.get("thread_id", "")
        provider = (agent_doc.get("provider") or agent_service.provider or "azure_foundry").strip().lower()
        model = agent_doc.get("model", "gpt-4.1-mini")

        if not thread_id or (provider == "azure_foundry" and not foundry_agent_id):
            logger.warning("Agent %s: missing foundry_agent_id or thread_id — skipping", agent_id)
            conn.logout()
            return

        highest_uid = last_seen_uid
        processed_count = 0

        # Ensure the agent has the email_trigger tool so it can
        # fetch full email bodies on demand via read_trigger_email.
        agent_tools = list(agent_doc.get("tools", []))
        if "email_trigger" not in agent_tools:
            agent_tools.append("email_trigger")

        for em in new_emails:
            uid = em["uid"]
            if uid > highest_uid:
                highest_uid = uid

            email_context = (
                f"[Gmail Push Notification — New Email]\n"
                f"From: {em['from']}\n"
                f"Subject: {em['subject']}\n"
                f"Date: {em['date']}\n"
                f"Email UID: {uid}\n\n"
                f"(Use the read_trigger_email tool with this UID to read the full email body if needed.)\n\n"
                f"---\n"
                f"Trigger instruction: {prompt}"
            )

            logger.info(
                "Agent %s: firing for email UID %d from %s subj=%s",
                agent_id, uid, em['from'], em['subject'][:50],
            )

            try:
                result = agent_service.run_non_streaming(
                    agent_id=agent_id,
                    foundry_agent_id=foundry_agent_id,
                    thread_id=thread_id,
                    model=model,
                    content=email_context,
                    tools=agent_tools,
                    provider=provider,
                    custom_instructions=agent_doc.get("custom_instructions", ""),
                )
                processed_count += 1
                logger.info(
                    "Agent %s gmail push complete for UID %d: %d chars",
                    agent_id, uid, len(result) if result else 0,
                )

                # If the run returned an error-like fallback (run failed/
                # cancelled/expired), stop processing remaining emails to
                # avoid cascading failures (e.g. rate-limit storms).
                if result and ("run failed" in result.lower() or "rate limit" in result.lower() or "timed out" in result.lower()):
                    logger.warning(
                        "Agent %s: run returned error for UID %d — backing off, will retry remaining emails next tick",
                        agent_id, uid,
                    )
                    break
            except Exception as e:
                logger.error("Agent %s: failed to fire for UID %d: %s — backing off", agent_id, uid, e)
                # Stop on first exception as well (network errors, etc.)
                break

        # Always save progress (highest UID) even if some emails failed,
        # so we don't re-process the ones we already sent to the agent.
        conn.logout()
        agent_store.update_gmail_push_after_run(agent_id, highest_uid, processed_count)


# ── IMAP helpers (module level) ─────────────────────────────────

def _decode_header_value(raw: str | None) -> str:
    if not raw:
        return ""
    parts = decode_header(raw)
    decoded = []
    for data, charset in parts:
        if isinstance(data, bytes):
            decoded.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(data)
    return " ".join(decoded)


def _get_text_from_message(msg: email_lib.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    return f"[HTML] {payload.decode(part.get_content_charset() or 'utf-8', errors='replace')[:2000]}"
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return ""


def _fetch_new_emails(
    conn: imaplib.IMAP4_SSL,
    *,
    last_seen_uid: int,
    filter_from: str = "",
    filter_subject: str = "",
    filter_body: str = "",
    filter_header: str = "",
    max_age_minutes: int = 0,
    filter_after_date: str = "",
) -> list[dict[str, Any]]:
    """
    Fetch emails with UID > last_seen_uid from the INBOX.
    Optionally filter by sender, subject, body keyword, header keyword, and age.
    Returns a list of dicts with uid, from, subject, date, body.
    """
    # Search for emails with UID greater than last_seen_uid
    if last_seen_uid > 0:
        search_criteria = f"UID {last_seen_uid + 1}:*"
    else:
        # First run: only check UNSEEN to avoid firing on all historic mail
        search_criteria = "UNSEEN"

    # Build additional IMAP search criteria
    imap_criteria_parts = []
    if filter_from:
        imap_criteria_parts.append(f'FROM "{filter_from}"')
    if filter_subject:
        imap_criteria_parts.append(f'SUBJECT "{filter_subject}"')
    # Server-side date filter (IMAP SINCE uses dd-Mon-yyyy, date-only
    # granularity).  This dramatically reduces the number of emails
    # fetched on first run.
    if filter_after_date:
        try:
            fad = filter_after_date.strip()
            if "." in fad and "-" not in fad:
                parts = fad.split(".")
                if len(parts) == 3:
                    day, month, year = parts
                    _dt = datetime(int(year), int(month), int(day))
                else:
                    _dt = datetime.fromisoformat(fad)
            else:
                _dt = datetime.fromisoformat(fad)
            # IMAP date format: dd-Mon-yyyy
            imap_date = _dt.strftime("%d-%b-%Y")
            imap_criteria_parts.append(f'SINCE {imap_date}')
            logger.debug("IMAP SINCE filter: %s", imap_date)
        except Exception as e:
            logger.warning("Could not build IMAP SINCE from filter_after_date '%s': %s", filter_after_date, e)

    if last_seen_uid > 0:
        # Use UID SEARCH
        if imap_criteria_parts:
            full_criteria = f"({' '.join(imap_criteria_parts)})"
            status, data = conn.uid("SEARCH", None, full_criteria, f"UID {last_seen_uid + 1}:*")
        else:
            status, data = conn.uid("SEARCH", None, f"UID {last_seen_uid + 1}:*")
    else:
        if imap_criteria_parts:
            full_criteria = f"UNSEEN {' '.join(imap_criteria_parts)}"
            status, data = conn.uid("SEARCH", None, full_criteria)
        else:
            status, data = conn.uid("SEARCH", None, "UNSEEN")

    if status != "OK" or not data or not data[0]:
        return []

    uid_list = data[0].split()
    if not uid_list:
        return []

    # Limit to 10 emails per tick to avoid overloading
    uid_list = uid_list[:10]

    results = []
    for uid_bytes in uid_list:
        uid = int(uid_bytes)

        # Skip if somehow <= last_seen_uid (IMAP quirk: UID range
        # "N:*" always returns at least UID N even if it already exists)
        if last_seen_uid > 0 and uid <= last_seen_uid:
            continue

        status, msg_data = conn.uid("FETCH", uid_bytes, "(RFC822)")
        if status != "OK" or not msg_data or not msg_data[0]:
            continue

        raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
        msg = email_lib.message_from_bytes(raw)

        from_addr = _decode_header_value(msg["From"])
        subject = _decode_header_value(msg["Subject"])

        # Apply filters (double-check, IMAP search may be fuzzy)
        if filter_from and filter_from.lower() not in from_addr.lower():
            continue
        if filter_subject and filter_subject.lower() not in subject.lower():
            continue

        # Age filter — skip emails older than max_age_minutes
        if max_age_minutes > 0:
            date_str = msg["Date"]
            if date_str:
                try:
                    email_dt = parsedate_to_datetime(date_str)
                    if email_dt.tzinfo is None:
                        email_dt = email_dt.replace(tzinfo=timezone.utc)
                    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
                    if email_dt < cutoff:
                        logger.debug("Skipping UID %d — too old (%s)", uid, date_str)
                        continue
                except Exception:
                    pass  # if we can't parse date, don't filter

        # Absolute date filter — skip emails before filter_after_date
        if filter_after_date:
            date_str = msg["Date"]
            if date_str:
                try:
                    email_dt = parsedate_to_datetime(date_str)
                    if email_dt.tzinfo is None:
                        email_dt = email_dt.replace(tzinfo=timezone.utc)
                    # Parse the filter date — supports ISO 8601 (YYYY-MM-DD) and
                    # European d.m.YYYY formats
                    fad = filter_after_date.strip()
                    if "." in fad and "-" not in fad:
                        # European format: d.m.YYYY or dd.mm.YYYY
                        parts = fad.split(".")
                        if len(parts) == 3:
                            day, month, year = parts
                            cutoff_date = datetime(
                                int(year), int(month), int(day),
                                tzinfo=timezone.utc,
                            )
                        else:
                            cutoff_date = datetime.fromisoformat(fad).replace(tzinfo=timezone.utc)
                    else:
                        cutoff_date = datetime.fromisoformat(fad)
                        if cutoff_date.tzinfo is None:
                            cutoff_date = cutoff_date.replace(tzinfo=timezone.utc)
                    if email_dt < cutoff_date:
                        logger.debug(
                            "Skipping UID %d — before filter_after_date %s (email date: %s)",
                            uid, filter_after_date, date_str,
                        )
                        continue
                except Exception as e:
                    logger.warning("Failed to parse filter_after_date '%s': %s", filter_after_date, e)

        # Header keyword filter — check all header values
        if filter_header:
            header_kw = filter_header.lower()
            header_match = False
            for key in msg.keys():
                val = _decode_header_value(msg[key])
                if header_kw in val.lower():
                    header_match = True
                    break
            if not header_match:
                continue

        body = _get_text_from_message(msg)

        # Body keyword filter
        if filter_body and filter_body.lower() not in body.lower():
            continue

        results.append({
            "uid": uid,
            "from": from_addr,
            "subject": subject,
            "date": msg["Date"] or "",
            "body": body,
        })

    return results


gmail_push_service = GmailPushService()
