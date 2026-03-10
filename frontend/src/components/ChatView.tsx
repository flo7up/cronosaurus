import { useState, useRef, useEffect, useMemo, type ReactNode } from "react";
import type { Message, AgentTrigger, Agent, ToolStep, MCPServer, TodoItem, EmailAccount, ToolCatalogEntry } from "../types/chat";
import ModelSelector from "./ModelSelector";

/* ── Instant Tooltip ─────────────────────────────────────────── */
function Tooltip({ text, children }: { text?: string; children: ReactNode }) {
  if (!text) return <>{children}</>;
  return (
    <div className="relative group/tip">
      {children}
      <div className="terminal-panel pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 -translate-x-1/2 whitespace-nowrap px-2.5 py-1 text-[11px] text-[#dcca8a] opacity-0 scale-95 group-hover/tip:opacity-100 group-hover/tip:scale-100 transition-all duration-150 shadow-lg">
        {text}
        <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-px border-4 border-transparent border-t-[#6a5421]" />
      </div>
    </div>
  );
}

interface ChatViewProps {
  messages: Message[];
  messagesLoading: boolean;
  streamingContent: string;
  streamingToolSteps: ToolStep[];
  streamingTodos: TodoItem[];
  streamingImages: Array<{ data: string; media_type: string }>;
  isStreaming: boolean;
  onSend: (content: string, images?: Array<{ data: string; media_type: string }>) => void;
  onStop: () => void;
  onToggleSidebar: () => void;
  activeAgent: Agent | null;
  serviceReady: boolean | null;
  onNewAgent: () => void;
  models: string[];
  selectedModel: string;
  onModelChange: (model: string) => void;
  onOpenManagement: (tab: string) => void;
  onRenameAgent: (name: string) => void;
  onToolsChange: (tools: string[]) => void;
  toolLibrary: string[];
  mcpServers: MCPServer[];
  agentBusy?: boolean;
  emailAccounts: EmailAccount[];
  onEmailAccountChange: (accountId: string | null) => void;
  onNewAgentWithPrompt: (prompt: string) => void;
  toolCatalog: ToolCatalogEntry[];
  onCustomInstructionsChange: (instructions: string) => void;
}

export default function ChatView({
  messages,
  messagesLoading,
  streamingContent,
  streamingToolSteps,
  streamingTodos,
  streamingImages,
  isStreaming,
  onSend,
  onStop,
  onToggleSidebar,
  activeAgent,
  serviceReady,
  onNewAgent,
  models,
  selectedModel,
  onModelChange,
  onOpenManagement,
  onRenameAgent,
  onToolsChange,
  toolLibrary,
  mcpServers,
  agentBusy,
  emailAccounts,
  onEmailAccountChange,
  onNewAgentWithPrompt,
  toolCatalog,
  onCustomInstructionsChange,
}: ChatViewProps) {
  const [input, setInput] = useState("");
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null);
  const [attachedImages, setAttachedImages] = useState<Array<{ data: string; media_type: string; preview: string }>>([]);
  const [showInstructionsDialog, setShowInstructionsDialog] = useState(false);
  const [instructionsDraft, setInstructionsDraft] = useState("");
  const [lightboxImage, setLightboxImage] = useState<{ src: string } | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [input]);

  // Re-focus textarea when streaming finishes
  useEffect(() => {
    if (!isStreaming) {
      textareaRef.current?.focus();
    }
  }, [isStreaming]);

  // Estimate token count locally (avoids server round-trip)
  const tokenInfo = useMemo(() => {
    if (!activeAgent) return null;
    const model = activeAgent.model || "gpt-4.1-mini";
    // Approximate: ~0.75 tokens per character for English text
    let count = 0;
    for (const msg of messages) {
      count += 4; // per-message overhead
      if (msg.content) count += Math.ceil(msg.content.length / 4);
    }
    // Context limits by model
    const limits: Record<string, number> = {
      "gpt-4.1": 1_048_576, "gpt-4.1-mini": 1_048_576, "gpt-4.1-nano": 1_048_576,
      "gpt-5-mini": 1_048_576, "gpt-5-chat": 1_048_576, "gpt-5-nano": 1_048_576,
      "model-router": 1_048_576,
    };
    const limit = limits[model] ?? 128_000;
    return { count, limit };
  }, [activeAgent?.model, messages]);

  // Auto-focus textarea when switching to / creating an agent
  useEffect(() => {
    if (activeAgent) {
      // If there's a pending prompt from an example card, fill it in
      if (pendingPrompt) {
        setInput(pendingPrompt);
        setPendingPrompt(null);
      }
      requestAnimationFrame(() => textareaRef.current?.focus());
    }
  }, [activeAgent?.id]);

  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!trimmed && attachedImages.length === 0) return;
    if (isStreaming) {
      onStop();
    }
    const images = attachedImages.length > 0
      ? attachedImages.map(({ data, media_type }) => ({ data, media_type }))
      : undefined;
    onSend(trimmed || "What's in this image?", images);
    setInput("");
    setAttachedImages([]);
    requestAnimationFrame(() => textareaRef.current?.focus());
  };

  const processImageFile = (file: File) => {
    if (!file.type.startsWith("image/")) return;
    if (file.size > 20 * 1024 * 1024) return; // 20MB max
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      // result is "data:image/png;base64,iVBOR..."
      const [header, base64Data] = result.split(",");
      const mediaType = header.match(/data:(.*?);/)?.[1] || "image/png";
      setAttachedImages((prev) => [...prev, {
        data: base64Data,
        media_type: mediaType,
        preview: result,
      }]);
    };
    reader.readAsDataURL(file);
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of Array.from(items)) {
      if (item.type.startsWith("image/")) {
        e.preventDefault();
        const file = item.getAsFile();
        if (file) processImageFile(file);
        return;
      }
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const files = e.dataTransfer?.files;
    if (!files) return;
    for (const file of Array.from(files)) {
      if (file.type.startsWith("image/")) {
        processImageFile(file);
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Welcome screen
  if (!activeAgent) {
    return (
      <div className="app-content flex-1 flex flex-col items-center justify-center px-4 relative">
        <button
          onClick={onToggleSidebar}
          className="absolute top-4 left-4 p-2 text-[#b8ad78] hover:text-[#fff0b0] md:hidden"
        >
          <svg
            className="w-6 h-6"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 6h16M4 12h16M4 18h16"
            />
          </svg>
        </button>

        {/* Status banner */}
        {serviceReady === false && (
          <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-yellow-900/60 border border-yellow-700 rounded-lg px-4 py-2 text-sm text-yellow-200 max-w-md text-center">
            Agent service not configured. Set{" "}
            <code className="bg-yellow-800/50 px-1 rounded">
              PROJECT_ENDPOINT
            </code>{" "}
            in backend/.env
          </div>
        )}

        <div className="terminal-panel terminal-dot-grid mb-3 w-full max-w-2xl overflow-hidden rounded-md">
          <div className="terminal-titlebar">cronosaurus :: terminal</div>
          <div className="flex items-center gap-4 px-5 py-5">
            <img src="/logo.png" alt="Cronosaurus" className="h-12 w-12 rounded-md border border-amber-200/15 shadow-[0_0_0_1px_rgba(242,194,48,0.12)]" />
            <div>
              <h1 className="brand-display text-4xl font-bold text-[#fff0b0]">Cronosaurus</h1>
              <p className="mt-1 text-xs uppercase tracking-[0.22em] text-[#97ff8a]">interactive agent console</p>
            </div>
          </div>
        </div>
        <p className="mb-6 text-lg text-[#b8ad78]">
          Create an agent or try an example below
        </p>
        {models.length > 0 && (
          <div className="mb-6 flex items-center gap-3">
            <span className="text-sm text-[#c3b884]">Model:</span>
            <ModelSelector
              models={models}
              selectedModel={selectedModel}
              onChange={onModelChange}
            />
          </div>
        )}
        <button
          onClick={onNewAgent}
          className="brand-button-primary mb-8 px-6 py-3 font-semibold transition-all"
        >
          launch new agent
        </button>

        {/* Example use-case cards */}
        <div className="w-full max-w-2xl space-y-2 mb-6">
          <div className="terminal-label text-[#97ff8a] mb-3 px-1">quick start examples</div>
          {[
            {
              icon: "🌐",
              title: "Website change monitor",
              desc: "Scrape a website on a schedule and get email alerts when content changes",
              prompt: "Set up a recurring trigger that checks https://example.com every 30 minutes using web_fetch. Compare the page content with the previous version and send me an email notification if anything meaningful changed. Summarize what's different.",
            },
            {
              icon: "💰",
              title: "Azure cost digest",
              desc: "Get a daily summary of your Azure spending delivered to your inbox",
              prompt: "Create a daily trigger (every 1440 minutes) that pulls my Azure cost overview by resource group for the current month, formats it as a clean summary with totals and top spenders, and sends it to me via email with the subject 'Daily Azure Cost Report'.",
            },
            {
              icon: "📈",
              title: "Crypto price alerts",
              desc: "Monitor crypto prices and notify you when thresholds are hit",
              prompt: "Set up a trigger that runs every 15 minutes to check the price of BTC and ETH. If BTC drops below $90,000 or ETH drops below $3,000, send me a notification with the current prices and percentage change. Include a brief market context from a web search.",
            },
            {
              icon: "🔗",
              title: "Multi-source intelligence brief",
              desc: "Combine web scraping, market data, and email into an automated daily brief",
              prompt: "Create a daily trigger that: 1) Searches the web for the latest AI industry news, 2) Gets the current prices of BTC, ETH, and SOL, 3) Checks my Azure spending for today, and 4) Compiles everything into a clean morning briefing email with sections for News, Markets, and Cloud Costs. Send it with the subject 'Morning Intelligence Brief'.",
            },
          ].map((example, i) => (
            <button
              key={i}
              onClick={() => {
                setPendingPrompt(example.prompt);
                onNewAgentWithPrompt(example.prompt);
              }}
              className="terminal-control w-full flex items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-[#1b160f] group"
            >
              <span className="text-lg mt-0.5 shrink-0">{example.icon}</span>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-[#f6efc9] group-hover:text-[#fff0b0]">{example.title}</div>
                <div className="text-xs text-[#8b7f59] mt-0.5 group-hover:text-[#b8ad78]">{example.desc}</div>
              </div>
              <svg className="w-4 h-4 text-[#5f4c1d] group-hover:text-[#97ff8a] shrink-0 mt-1 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
            </button>
          ))}
        </div>

        <div className="flex gap-3">
          <span className="terminal-chip px-3 py-1 text-xs">
            Foundry Agent
          </span>
          <span className="terminal-chip border-lime-300/20 bg-[#12180f] text-[#b8d289] px-3 py-1 text-xs">
            Streaming
          </span>
          <span className="terminal-chip border-stone-300/10 bg-[#171511] text-[#d7cab1] px-3 py-1 text-xs">
            MCP Ready
          </span>
          <span className="terminal-chip border-orange-300/10 bg-[#25150b] text-[#ffb36c] px-3 py-1 text-xs">
            Triggers
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="app-content flex-1 flex flex-col relative">
      {/* Top bar */}
      <div className="terminal-panel mx-3 mt-3 flex items-center gap-3 px-4 py-3">
        <button
          onClick={onToggleSidebar}
          className="p-1.5 text-[#b8ad78] hover:text-[#fff0b0] md:hidden"
        >
          <svg
            className="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 6h16M4 12h16M4 18h16"
            />
          </svg>
        </button>
        <AgentNameEditor name={activeAgent.name} onRename={onRenameAgent} />
        {models.length > 0 && (
          <ModelSelector
            models={models}
            selectedModel={selectedModel}
            onChange={onModelChange}
            disabled={isStreaming}
          />
        )}
        {/* Tools dropdown */}
        {activeAgent && (
          <ToolsDropdown
            tools={activeAgent.tools}
            onChange={onToolsChange}
            toolLibrary={toolLibrary}
            mcpServers={mcpServers}
            onOpenManagement={onOpenManagement}
            emailAccounts={emailAccounts}
            selectedEmailAccountId={activeAgent.email_account_id}
            onEmailAccountChange={onEmailAccountChange}
            toolCatalog={toolCatalog}
          />
        )}
        {/* Agent instructions button */}
        <Tooltip text="Agent instructions">
          <button
            onClick={() => {
              setInstructionsDraft(activeAgent.custom_instructions || "");
              setShowInstructionsDialog(true);
            }}
            className={`terminal-control p-1.5 transition-colors ${
              activeAgent.custom_instructions
                ? "text-[#97ff8a] bg-[#121a0f] hover:bg-[#1a2515]"
                : "text-[#8b7f59] hover:text-[#dcca8a] hover:bg-[#18130d]"
            }`}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>
        </Tooltip>
        {/* Trigger button */}
        <button
          onClick={() => onOpenManagement("triggers")}
          className={`terminal-control p-1.5 transition-colors ${
            activeAgent.trigger?.active
              ? "text-amber-300 bg-[#22190d] hover:bg-[#2d2110]"
              : activeAgent.trigger
                ? "text-[#8b7f59] hover:text-[#dcca8a] hover:bg-[#18130d]"
                : "text-[#8b7f59] hover:text-[#dcca8a] hover:bg-[#18130d]"
          }`}
          title={
            activeAgent.trigger?.active
              ? `Trigger active: every ${activeAgent.trigger.interval_minutes}m`
              : activeAgent.trigger
                ? "Trigger paused"
                : "Set up trigger"
          }
        >
          <svg
            className="w-4 h-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </button>
        {serviceReady === false && (
          <span className="ml-auto terminal-chip px-2 py-1 text-[10px] text-yellow-300">
            Agent not connected
          </span>
        )}
      </div>

      {/* Trigger status bar */}
      {activeAgent.trigger && <TriggerStatusBar trigger={activeAgent.trigger} onOpenPanel={() => onOpenManagement("triggers")} />}

      {/* Processing banner when a trigger run is in progress */}
      {agentBusy && (
        <div className="terminal-panel mx-3 mt-3 flex items-center gap-2 px-4 py-2 text-xs text-[#97ff8a]">
          <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span>Processing a trigger run… Your messages will be sent once it completes.</span>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-4 py-6 space-y-6">
          {messagesLoading && messages.length === 0 && (
            <div className="flex items-center justify-center py-20">
              <svg className="animate-spin h-6 w-6 text-[#dcca8a]" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span className="ml-3 text-sm text-[#b8ad78]">Loading conversation log…</span>
            </div>
          )}
          {messages.map((msg, i) => (
            <MessageBubble key={i} message={msg} onImageClick={(src) => setLightboxImage({ src })} />
          ))}

          {/* Confirmation buttons — shown when the last assistant message used request_confirmation */}
          {!isStreaming && messages.length > 0 && (() => {
            const last = messages[messages.length - 1];
            if (last.role !== "assistant") return null;
            if (!last.toolSteps?.some(s => s.name === "request_confirmation")) return null;
            return (
              <div className="flex gap-3 ml-10">
                <button
                  onClick={() => onSend("yes")}
                  className="terminal-control border-lime-300/20 bg-[#12180f] px-4 py-2 text-[#97ff8a] text-sm font-medium transition-colors flex items-center gap-1.5"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  approve
                </button>
                <button
                  onClick={() => onSend("no")}
                  className="terminal-control px-4 py-2 text-[#dcca8a] text-sm font-medium transition-colors flex items-center gap-1.5"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                  reject
                </button>
              </div>
            );
          })()}

          {/* Streaming tool steps + assistant message */}
          {isStreaming && (streamingToolSteps.length > 0 || streamingContent || streamingTodos.length > 0 || streamingImages.length > 0) && (
            <div className="flex gap-3">
              <div className="w-7 h-7 shrink-0 mt-1">
                <BotIcon />
              </div>
              <div className="flex-1 min-w-0">
                {streamingToolSteps.length > 0 && (
                  <ToolStepsDisplay steps={streamingTodos.length > 0
                    ? streamingToolSteps.filter(s => s.name !== "create_todo_list" && s.name !== "update_todo_status")
                    : streamingToolSteps} />
                )}
                {streamingTodos.length > 0 && (
                  <TodoListDisplay todos={streamingTodos} />
                )}
                {streamingImages.length > 0 && (
                  <div className="flex gap-2 flex-wrap mb-2 max-w-[80%]">
                    {streamingImages.map((img, i) => {
                      const src = `data:${img.media_type};base64,${img.data}`;
                      return (
                        <img
                          key={i}
                          src={src}
                          alt={`Captured ${i + 1}`}
                          className="max-h-64 max-w-full rounded border border-[#97ff8a]/20 object-contain cursor-pointer hover:opacity-80 transition-opacity"
                          onClick={() => setLightboxImage({ src })}
                        />
                      );
                    })}
                  </div>
                )}
                {streamingContent && (
                  <div className="terminal-bubble mt-1 max-w-[80%] px-4 py-3 text-sm leading-relaxed text-[#e0f5d0]">
                    <div className="terminal-label mb-2 text-[#97ff8a]">cronosaurus@agent $</div>
                    <div className="whitespace-pre-wrap break-words" style={{lineHeight: '1.7'}}>
                      {streamingContent}
                      <span className="terminal-caret ml-1" />
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Typing indicator (only when no content yet and no tool steps) */}
          {isStreaming && !streamingContent && streamingToolSteps.length === 0 && (
            <div className="flex gap-3">
              <div className="w-7 h-7 shrink-0 mt-1">
                <BotIcon />
              </div>
              <div className="terminal-label flex items-center gap-2 pt-2 text-[#97ff8a]">
                <span className="w-2 h-2 bg-[#97ff8a] rounded-full animate-bounce [animation-delay:-0.3s]" />
                <span className="w-2 h-2 bg-[#97ff8a] rounded-full animate-bounce [animation-delay:-0.15s]" />
                <span className="w-2 h-2 bg-[#97ff8a] rounded-full animate-bounce" />
                streaming response
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input area */}
      <div className="p-3 pt-0">
        <div className="max-w-3xl mx-auto">
          <div
            className="terminal-panel terminal-dot-grid overflow-hidden"
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
          >
            <div className="terminal-titlebar">command input</div>

            {/* Image preview strip */}
            {attachedImages.length > 0 && (
              <div className="flex gap-2 px-4 pt-3 pb-1 flex-wrap">
                {attachedImages.map((img, i) => (
                  <div key={i} className="relative group">
                    <img
                      src={img.preview}
                      alt={`Attachment ${i + 1}`}
                      className="h-16 w-16 object-cover border border-[#f2c230]/20"
                    />
                    <button
                      onClick={() => setAttachedImages((prev) => prev.filter((_, j) => j !== i))}
                      className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-[#1a1510] border border-[#f2c230]/30 text-[#dcca8a] hover:text-red-400 flex items-center justify-center text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="flex items-end gap-3 px-4 py-3">
              <span className="terminal-label pb-1 text-[#97ff8a]">&gt;</span>
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              placeholder="type a command, question, or directive — paste or drop images"
              rows={1}
              className="flex-1 bg-transparent text-[#f6efc9] placeholder-[#786d48] resize-none
                focus:outline-none text-sm leading-6 max-h-[200px]"
            />
            {isStreaming && !input.trim() ? (
              /* Stop button — shown while streaming and input is empty */
              <button
                onClick={onStop}
                className="terminal-control p-2 text-[#dcca8a] hover:bg-[#1d1710]
                  transition-colors shrink-0"
                title="Stop generating"
              >
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                  <rect x="6" y="6" width="12" height="12" rx="2" />
                </svg>
              </button>
            ) : (
              <>
              {/* Upload image button */}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                multiple
                className="hidden"
                onChange={(e) => {
                  const files = e.target.files;
                  if (files) {
                    for (const file of Array.from(files)) processImageFile(file);
                  }
                  e.target.value = "";
                }}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                className="terminal-control p-2 text-[#8b7f59] hover:text-[#dcca8a] hover:bg-[#1d1710]
                  transition-colors shrink-0"
                title="Attach image"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0022.5 18.75V5.25A2.25 2.25 0 0020.25 3H3.75A2.25 2.25 0 001.5 5.25v13.5A2.25 2.25 0 003.75 21z" />
                </svg>
              </button>
              {/* Send button */}
              <button
                onClick={handleSubmit}
                disabled={!input.trim() && attachedImages.length === 0}
                className="brand-button-primary p-2
                  disabled:opacity-30 disabled:cursor-not-allowed
                  transition-colors shrink-0"
              >
                <svg
                  className="w-4 h-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"
                  />
                </svg>
              </button>
              </>
            )}
            </div>
          </div>
          <p className="text-xs text-[#786d48] text-center mt-2 uppercase tracking-[0.16em] flex items-center justify-center gap-3">
            <span>session target: microsoft foundry agent service</span>
            {tokenInfo && tokenInfo.limit > 0 && (
              <span className="inline-flex items-center gap-1.5 normal-case tracking-normal">
                <span
                  className="inline-block w-1.5 h-1.5 rounded-full"
                  style={{
                    backgroundColor:
                      tokenInfo.count / tokenInfo.limit > 0.9
                        ? "#ef4444"
                        : tokenInfo.count / tokenInfo.limit > 0.7
                          ? "#f59e0b"
                          : "#97ff8a",
                  }}
                />
                {tokenInfo.count >= 1000
                  ? `${(tokenInfo.count / 1000).toFixed(1)}k`
                  : tokenInfo.count}
                {" / "}
                {tokenInfo.limit >= 1_000_000
                  ? `${(tokenInfo.limit / 1_000_000).toFixed(0)}M`
                  : tokenInfo.limit >= 1000
                    ? `${(tokenInfo.limit / 1000).toFixed(0)}k`
                    : tokenInfo.limit}
                {" tokens"}
              </span>
            )}
          </p>
        </div>
      </div>

      {/* Instructions dialog */}
      {showInstructionsDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onMouseDown={(e) => { if (e.target === e.currentTarget) setShowInstructionsDialog(false); }}>
          <div className="terminal-panel mx-4 resize overflow-auto" style={{ width: 540, minWidth: 320, minHeight: 280, maxWidth: '90vw', maxHeight: '90vh' }}>
            <div className="terminal-titlebar flex items-center justify-between">
              <span>agent instructions</span>
              <button onClick={() => setShowInstructionsDialog(false)} className="text-[#8b7f59] hover:text-[#dcca8a] transition-colors">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-4 space-y-3">
              <p className="text-xs text-[#8b7f59]">
                Custom instructions that shape how this agent behaves. These are prepended to the system prompt.
              </p>
              <textarea
                value={instructionsDraft}
                onChange={(e) => setInstructionsDraft(e.target.value)}
                placeholder="e.g. Always respond in Spanish. Be concise and use bullet points."
                className="w-full bg-[#0d0b08] border border-[#3d3520] rounded px-3 py-2 text-sm text-[#f6efc9] placeholder-[#5f4c1d] resize-y focus:outline-none focus:border-[#6a5421]"
                style={{ minHeight: 120, height: 200 }}
              />
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setShowInstructionsDialog(false)}
                  className="terminal-control px-3 py-1.5 text-xs text-[#8b7f59] hover:text-[#dcca8a]"
                >
                  Cancel
                </button>
                <button
                  onClick={() => {
                    onCustomInstructionsChange(instructionsDraft);
                    setShowInstructionsDialog(false);
                  }}
                  className="brand-button-primary px-4 py-1.5 text-xs font-medium"
                >
                  Save
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Image lightbox */}
      {lightboxImage && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 cursor-zoom-out"
          onClick={() => setLightboxImage(null)}
        >
          <img
            src={lightboxImage.src}
            alt="Full size"
            className="max-w-[95vw] max-h-[95vh] object-contain"
            onClick={(e) => e.stopPropagation()}
          />
          <button
            onClick={() => setLightboxImage(null)}
            className="absolute top-4 right-4 text-white/70 hover:text-white transition-colors"
          >
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Countdown hook ─────────────────────────────────────────── */

function useCountdown(targetIso: string | null): string {
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (!targetIso) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [targetIso]);

  if (!targetIso) return "";
  const diff = new Date(targetIso).getTime() - now;
  if (diff <= 0) return "any moment";
  const totalSec = Math.floor(diff / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

/* ── Trigger status bar ────────────────────────────────────── */

function TriggerStatusBar({
  trigger,
  onOpenPanel,
}: {
  trigger: AgentTrigger;
  onOpenPanel: () => void;
}) {
  const isGmailPush = trigger.type === "gmail_push";
  const countdown = useCountdown(trigger.active && !isGmailPush ? trigger.next_run : null);

  const intervalLabel = useMemo(() => {
    if (isGmailPush) return "";
    const mins = trigger.interval_minutes;
    if (mins < 60) return `${mins}m`;
    if (mins < 1440) return `${Math.floor(mins / 60)}h ${mins % 60 ? `${mins % 60}m` : ""}`.trim();
    const d = Math.floor(mins / 1440);
    const rem = mins % 1440;
    return `${d}d${rem ? ` ${Math.floor(rem / 60)}h` : ""}`;
  }, [trigger.interval_minutes, isGmailPush]);

  const accentActive = isGmailPush ? "terminal-panel text-red-300 hover:bg-red-950/30" : "terminal-panel text-[#dcca8a] hover:bg-[#18130d]";
  const dotColor = isGmailPush ? "bg-red-400" : "bg-amber-400";

  return (
    <button
      onClick={onOpenPanel}
      className={`
        flex items-center gap-2 px-4 py-1.5 text-xs w-full transition-colors
        ${
          trigger.active
            ? accentActive
            : "terminal-panel text-[#8b7f59] hover:bg-[#18130d]"
        }
      `}
    >
      {/* Pulsing dot for active */}
      {trigger.active ? (
        <span className="relative flex h-2 w-2 shrink-0">
          <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${dotColor} opacity-75`} />
          <span className={`relative inline-flex rounded-full h-2 w-2 ${dotColor}`} />
        </span>
      ) : (
        <span className="h-2 w-2 rounded-full bg-gray-600 shrink-0" />
      )}

      {/* Label */}
      <span className="font-medium">
        {trigger.active
          ? isGmailPush
            ? "Gmail push active"
            : "Trigger active"
          : isGmailPush
            ? "Gmail push paused"
            : "Trigger paused"}
      </span>

      {/* Type + interval */}
      <span className="text-[10px] opacity-70">
        {isGmailPush
          ? `Gmail push${trigger.filter_from ? ` · from ${trigger.filter_from}` : ""}`
          : `Recurring · every ${intervalLabel}`}
      </span>

      {/* Description if any */}
      {trigger.description && (
        <span className="truncate max-w-[200px] opacity-60 hidden sm:inline">
          — {trigger.description}
        </span>
      )}

      {/* Countdown / next run (only for scheduled triggers) */}
      {trigger.active && !isGmailPush && countdown && (
        <span className="ml-auto flex items-center gap-1 font-mono tabular-nums text-amber-400/90">
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {countdown}
        </span>
      )}

      {/* Watching label for gmail push */}
      {trigger.active && isGmailPush && (
        <span className="ml-auto flex items-center gap-1 text-red-400/90">
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
          </svg>
          watching
        </span>
      )}

      {/* Paused label */}
      {!trigger.active && (
        <span className="ml-auto text-gray-600">paused</span>
      )}

      {/* Run count */}
      {trigger.run_count > 0 && (
        <span className="opacity-50">
          ({trigger.run_count} run{trigger.run_count !== 1 ? "s" : ""})
        </span>
      )}
    </button>
  );
}

/* ── Agent name editor ──────────────────────────────────────── */

/* ── Tools dropdown ────────────────────────────────────────────── */

/* Static icon map for known tool IDs. Unknown tools get a generic icon. */
const TOOL_ICONS: Record<string, React.ReactNode> = {
  crypto: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  stock: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
    </svg>
  ),
  email_send: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
    </svg>
  ),
  email_read: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
    </svg>
  ),
  triggers: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  web_search: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
    </svg>
  ),
  polymarket: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M3.75 3v11.25A2.25 2.25 0 006 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0118 16.5h-2.25m-7.5 0h7.5m-7.5 0l-1 3m8.5-3l1 3m0 0l.5 1.5m-.5-1.5h-9.5m0 0l-.5 1.5m.75-9l3-3 2.148 2.148A12.061 12.061 0 0116.5 7.605" />
    </svg>
  ),
  azure_costs: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M2.25 18.75a60.07 60.07 0 0115.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 013 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 00-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 01-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 003 15h-.75M15 10.5a3 3 0 11-6 0 3 3 0 016 0zm3 0h.008v.008H18V10.5zm-12 0h.008v.008H6V10.5z" />
    </svg>
  ),
  weather: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M2.25 15a4.5 4.5 0 004.5 4.5H18a3.75 3.75 0 001.332-7.257 3 3 0 00-3.758-3.848 5.25 5.25 0 00-10.233 2.33A4.502 4.502 0 002.25 15z" />
    </svg>
  ),
  notifications: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
    </svg>
  ),
  code_interpreter: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5" />
    </svg>
  ),
  twitch_capture: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
    </svg>
  ),
  agent_collab: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z" />
    </svg>
  ),
};

/* Generic icon for tools without a specific icon */
const GENERIC_TOOL_ICON = (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
      d="M11.42 15.17l-5.1-3.56a1 1 0 00-.86-.08l-2.86.94a1 1 0 01-1.28-.7l-.54-2.26a1 1 0 01.7-1.19l2.89-.78a1 1 0 00.65-.54l1.35-2.88a1 1 0 011.56-.35l2.18 1.9a1 1 0 00.88.2l2.92-.62a1 1 0 011.13.76l.54 2.26a1 1 0 01-.44 1.08l-2.44 1.56a1 1 0 00-.46.76l-.16 2.97a1 1 0 01-1.14.92l-2.26-.42a1 1 0 00-.68.12z" />
  </svg>
);

const MCP_ICON = (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
      d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7m0 0a3 3 0 01-3 3m0 3h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008zm-3 6h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008z" />
  </svg>
);

function ToolsDropdown({
  tools,
  onChange,
  toolLibrary,
  mcpServers,
  onOpenManagement,
  emailAccounts,
  selectedEmailAccountId,
  onEmailAccountChange,
  toolCatalog,
}: {
  tools: string[];
  onChange: (tools: string[]) => void;
  toolLibrary: string[];
  mcpServers: MCPServer[];
  onOpenManagement: (tab: string) => void;
  emailAccounts: EmailAccount[];
  selectedEmailAccountId: string | null;
  onEmailAccountChange: (accountId: string | null) => void;
  toolCatalog: ToolCatalogEntry[];
}) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  // Build tool entries dynamically from the catalog + MCP servers
  const allToolsWithMcp = useMemo(() => {
    // Start from the backend catalog (includes all registered tools — built-in, custom, etc.)
    const catalogEntries = toolCatalog
      .filter((t) => t.category !== "mcp") // MCP handled separately below
      .map((t) => ({
        id: t.id,
        label: t.label,
        description: t.description,
        icon: TOOL_ICONS[t.id] || GENERIC_TOOL_ICON,
      }));

    // Add active MCP servers
    const mcpEntries = (mcpServers ?? []).filter(s => s.active).map((srv) => ({
      id: `mcp:${srv.id}`,
      label: srv.name,
      description: srv.description || `MCP server: ${srv.name}`,
      icon: MCP_ICON,
    }));

    return [...catalogEntries, ...mcpEntries];
  }, [toolCatalog, mcpServers]);

  const availableTools = allToolsWithMcp.filter((t) => toolLibrary.includes(t.id));

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (
        menuRef.current &&
        !menuRef.current.contains(e.target as Node) &&
        buttonRef.current &&
        !buttonRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  const toggle = (id: string) => {
    const next = tools.includes(id)
      ? tools.filter((t) => t !== id)
      : [...tools, id];
    onChange(next);
  };

  return (
    <>
      <div className="relative">
      <button
        ref={buttonRef}
        onClick={() => setOpen(!open)}
        className={`terminal-control p-1.5 transition-colors ${
          open
            ? "bg-[#22190e] text-[#fff0b0]"
            : "text-[#8b7f59] hover:text-[#dcca8a] hover:bg-[#18130d]"
        }`}
        title="Agent tools"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M11.42 15.17l-5.1-3.56a1 1 0 00-.86-.08l-2.86.94a1 1 0 01-1.28-.7l-.54-2.26a1 1 0 01.7-1.19l2.89-.78a1 1 0 00.65-.54l1.35-2.88a1 1 0 011.56-.35l2.18 1.9a1 1 0 00.88.2l2.92-.62a1 1 0 011.13.76l.54 2.26a1 1 0 01-.44 1.08l-2.44 1.56a1 1 0 00-.46.76l-.16 2.97a1 1 0 01-1.14.92l-2.26-.42a1 1 0 00-.68.12z" />
        </svg>
      </button>
      {/* Badge */}
      {(() => {
        const visibleEnabled = tools.filter(t => availableTools.some(at => at.id === t)).length;
        return visibleEnabled > 0 && !open ? (
          <span className="absolute -top-1 -right-1 w-4 h-4 text-[9px] font-bold flex items-center justify-center rounded-full bg-[#97ff8a] text-[#120f07] pointer-events-none">
            {visibleEnabled}
          </span>
        ) : null;
      })()}
      </div>

      {/* Slide-in panel — covers the left side of the chat area */}
      {open && (
        <>
          {/* Backdrop — only covers the chat area, not the sidebar */}
          <div
            className="fixed top-0 right-0 bottom-0 left-0 md:left-[288px] bg-black/40 z-40"
            onClick={() => setOpen(false)}
          />

          {/* Clip container — prevents panel from visually overlapping the sidebar */}
          <div className="fixed top-0 right-0 bottom-0 left-0 md:left-[288px] z-50 overflow-hidden pointer-events-none">
            {/* Panel */}
            <div
              ref={menuRef}
              className="absolute top-0 left-0 bottom-0 w-full max-w-md app-sidebar border-r border-[#f2c230]/18 shadow-2xl flex flex-col animate-slide-in-left pointer-events-auto"
              style={{ animationDuration: '150ms' }}
            >
            <div className="terminal-titlebar px-4">
              <span className="flex-1">agent tools</span>
              <button
                onClick={() => setOpen(false)}
                className="text-[#786d48] hover:text-[#dcca8a] transition-colors ml-auto"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="px-4 py-3 border-b border-[#f2c230]/10">
              <span className="text-xs font-medium text-[#b8ad78] uppercase tracking-wider">toggle capabilities</span>
              <span className="text-xs text-[#786d48] ml-2">({availableTools.length} available)</span>
            </div>

            {/* Scrollable tool list */}
            <div className="flex-1 overflow-y-auto">
              {availableTools.map((tool) => {
                const enabled = tools.includes(tool.id);
                const isEmailTool = tool.id === "email_send" || tool.id === "email_read";
                const activeAccount = isEmailTool && enabled && emailAccounts.length > 0
                  ? emailAccounts.find(a => a.id === selectedEmailAccountId) || emailAccounts.find(a => a.is_default) || emailAccounts[0]
                  : null;
                return (
                  <div key={tool.id}>
                    <button
                      onClick={() => toggle(tool.id)}
                      className="w-full flex items-center gap-3 px-4 py-3 hover:bg-[#1b160f] transition-colors"
                    >
                      <span className={`shrink-0 ${enabled ? "text-[#97ff8a]" : "text-[#786d48]"}`}>{tool.icon}</span>
                      <div className="flex-1 text-left min-w-0">
                        <div className={`text-sm ${enabled ? "text-[#f6efc9]" : "text-[#9b8f64]"}`}>{tool.label}</div>
                        <div className="text-xs text-[#6d6242] truncate">
                          {isEmailTool && activeAccount
                            ? activeAccount.from_email || activeAccount.label
                            : tool.description}
                        </div>
                      </div>
                      <div
                        className={`w-9 h-5 transition-colors relative flex-shrink-0 border ${
                          enabled ? "bg-[#152212] border-[#97ff8a]/40" : "bg-[#16120c] border-[#5f4c1d]"
                        }`}
                      >
                        <span
                          className={`absolute top-0.5 w-4 h-4 bg-[#f6efc9] shadow transition-transform ${
                            enabled ? "left-[18px]" : "left-0.5"
                          }`}
                        />
                      </div>
                    </button>
                  </div>
                );
              })}
            </div>

            {/* Email account selector */}
            {emailAccounts.length > 1 && tools.some(t => t === "email_send" || t === "email_read") && (
              <div className="px-4 py-3 border-t border-[#f2c230]/10">
                <div className="terminal-label text-[#97ff8a] mb-2">email account</div>
                <div className="space-y-1">
                  {emailAccounts.map(acct => {
                    const isSelected = selectedEmailAccountId
                      ? acct.id === selectedEmailAccountId
                      : acct.is_default;
                    return (
                      <button
                        key={acct.id}
                        onClick={() => onEmailAccountChange(acct.id)}
                        className={`w-full flex items-center gap-2 px-3 py-2 text-left transition-colors ${
                          isSelected
                            ? "terminal-control bg-[#152212] border-[#97ff8a]/30 text-[#e0f5d0]"
                            : "terminal-control text-[#9b8f64] hover:bg-[#1b160f] hover:text-[#dcca8a]"
                        }`}
                      >
                        <span className={`w-2 h-2 shrink-0 ${isSelected ? "bg-[#97ff8a]" : "bg-[#5f4c1d]"}`} />
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-medium truncate">{acct.label || acct.from_email}</div>
                          {acct.label && <div className="text-[10px] text-[#786d48] truncate">{acct.from_email}</div>}
                        </div>
                        {acct.is_default && !selectedEmailAccountId && (
                          <span className="terminal-chip text-[9px] px-1.5 py-0.5 text-[#97ff8a]">default</span>
                        )}
                        {isSelected && selectedEmailAccountId && (
                          <svg className="w-3.5 h-3.5 text-[#97ff8a] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Footer */}
            <div className="border-t border-[#f2c230]/10">
              <button
                onClick={() => { setOpen(false); onOpenManagement("tools"); }}
                className="w-full flex items-center gap-2 px-4 py-3 text-xs text-[#97ff8a] hover:text-[#c3ffba] hover:bg-[#18130d] transition-colors"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.5v15m7.5-7.5h-15" />
                </svg>
                Manage tools in settings…
              </button>
            </div>
          </div>
          </div>{/* close clip container */}
        </>
      )}
    </>
  );
}

function AgentNameEditor({
  name,
  onRename,
}: {
  name: string;
  onRename: (newName: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setDraft(name);
  }, [name]);

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  const commit = () => {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== name) onRename(trimmed);
    else setDraft(name);
    setEditing(false);
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") { setDraft(name); setEditing(false); }
        }}
        className="terminal-control w-56 px-2 py-1 text-sm"
      />
    );
  }

  return (
    <div className="flex items-center gap-1.5 group">
      <span className="text-sm text-[#f6efc9] truncate max-w-[200px] terminal-label normal-case tracking-[0.04em]">
        {name}
      </span>
      <button
        onClick={() => setEditing(true)}
        className="p-0.5 text-[#786d48] opacity-0 group-hover:opacity-100 hover:text-[#fff0b0] transition-all"
        title="Rename agent"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
        </svg>
      </button>
    </div>
  );
}

/* ── Sub-components ────────────────────────────────────────────── */

function BotIcon() {
  return (
    <img src="/logo.png" alt="Cronosaurus" className="w-7 h-7 rounded-full" />
  );
}

function UserIcon() {
  return (
    <svg
      className="w-4 h-4 text-white"
      fill="currentColor"
      viewBox="0 0 24 24"
    >
      <path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z" />
    </svg>
  );
}

function MessageBubble({
  message,
  isStreaming = false,
  onImageClick,
}: {
  message: Message;
  isStreaming?: boolean;
  onImageClick?: (src: string) => void;
}) {
  const isUser = message.role === "user";
  const tooltip = message.created_at
    ? new Date(message.created_at).toLocaleString()
    : undefined;

  if (isUser) {
    return (
      <div className="flex gap-3 justify-end">
        <div className="max-w-[80%]">
          <div className="terminal-label mb-2 text-right text-[#f2c230]">operator@local &gt;</div>
          <div className="terminal-bubble-user px-4 py-3 text-sm leading-relaxed text-[#fff5cf]">
          {message.images && message.images.length > 0 && (
            <div className="flex gap-2 flex-wrap mb-2">
              {message.images.map((img, i) => {
                const src = `data:${img.media_type};base64,${img.data}`;
                return (
                  <img
                    key={i}
                    src={src}
                    alt={`Attachment ${i + 1}`}
                    className="max-h-48 max-w-full border border-[#f2c230]/20 object-contain cursor-pointer hover:opacity-80 transition-opacity"
                    onClick={() => onImageClick?.(src)}
                  />
                );
              })}
            </div>
          )}
          <div className="whitespace-pre-wrap break-words" style={{lineHeight: '1.7'}}>{message.content}</div>
          </div>
        </div>
        <Tooltip text={tooltip}>
          <div
            className="w-7 h-7 rounded-full bg-[#3f2d08] border border-amber-200/20 flex items-center justify-center shrink-0 mt-1 cursor-default hover:ring-2 hover:ring-amber-300/40 transition-all duration-150"
          >
            <UserIcon />
          </div>
        </Tooltip>
      </div>
    );
  }

  const botTooltip = message.created_at
    ? new Date(message.created_at).toLocaleString()
    : undefined;

  return (
    <div className="flex gap-3">
      <Tooltip text={botTooltip}>
        <div
          className="w-7 h-7 shrink-0 mt-1 cursor-default hover:ring-2 hover:ring-[#97ff8a]/30 rounded-full transition-all duration-150 bg-[#0e1a0e] border border-[#97ff8a]/25"
        >
          <BotIcon />
        </div>
      </Tooltip>
      <div className="flex-1 min-w-0">
        {/* Tool steps (if any) — filter out todo chips when a todo list is present */}
        {(() => {
          const todos = extractTodosFromSteps(message.toolSteps);
          const filteredSteps = todos
            ? message.toolSteps?.filter(s => s.name !== "create_todo_list" && s.name !== "update_todo_status")
            : message.toolSteps;
          return (
            <>
              {filteredSteps && filteredSteps.length > 0 && (
                <ToolStepsDisplay steps={filteredSteps} />
              )}
              {todos && <TodoListDisplay todos={todos} />}
            </>
          );
        })()}
        <div className="max-w-[80%]">
          <div className="terminal-label mb-2 text-[#97ff8a]">cronosaurus@agent $</div>
          {message.images && message.images.length > 0 && (
            <div className="flex gap-2 flex-wrap mb-2">
              {message.images.map((img, i) => {
                const src = `data:${img.media_type};base64,${img.data}`;
                return (
                  <img
                    key={i}
                    src={src}
                    alt={`Captured ${i + 1}`}
                    className="max-h-64 max-w-full rounded border border-[#97ff8a]/20 object-contain cursor-pointer hover:opacity-80 transition-opacity"
                    onClick={() => onImageClick?.(src)}
                  />
                );
              })}
            </div>
          )}
          <div className="terminal-bubble mt-1 px-4 py-3 text-sm leading-relaxed text-[#e0f5d0]">
          <div className="whitespace-pre-wrap break-words" style={{lineHeight: '1.7'}}>
            {message.content}
            {isStreaming && (
              <span className="terminal-caret ml-1" />
            )}
          </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Todo List Helpers ───────────────────────────────────────── */

/** Extract the final todo list state from a message's tool steps. */
function extractTodosFromSteps(steps?: ToolStep[]): TodoItem[] | null {
  if (!steps) return null;
  for (let i = steps.length - 1; i >= 0; i--) {
    const r = steps[i].result as Record<string, unknown> | undefined;
    if (
      (steps[i].name === "create_todo_list" || steps[i].name === "update_todo_status") &&
      r?.todos &&
      Array.isArray(r.todos)
    ) {
      return r.todos as TodoItem[];
    }
  }
  return null;
}

/** Renders an inline todo list with real-time status indicators. */
function TodoListDisplay({ todos }: { todos: TodoItem[] }) {
  const completed = todos.filter(t => t.status === "completed").length;
  const failed = todos.filter(t => t.status === "failed").length;
  const total = todos.length;
  const allDone = completed + failed === total;

  return (
    <div className="terminal-panel my-2 max-w-[80%] overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-[#f2c230]/10">
        <svg className="w-3.5 h-3.5 text-[#97ff8a]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
        <span className="terminal-label text-[#97ff8a]">Task Queue</span>
        <span className="ml-auto text-xs text-[#8b7f59] tabular-nums">
          {completed}/{total}
          {failed > 0 && <span className="text-red-400"> ({failed} failed)</span>}
        </span>
        {allDone && (
          <svg className="w-3.5 h-3.5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        )}
      </div>
      {/* Items */}
      <div className="divide-y divide-[#f2c230]/10">
        {todos.map(todo => (
          <div key={todo.id} className="flex items-start gap-2.5 px-3 py-2">
            {/* Status icon */}
            {todo.status === "completed" && (
              <svg className="w-4 h-4 text-green-400 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            )}
            {todo.status === "in_progress" && (
              <svg className="w-4 h-4 text-blue-400 shrink-0 mt-0.5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            )}
            {todo.status === "failed" && (
              <svg className="w-4 h-4 text-red-400 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            )}
            {todo.status === "pending" && (
              <div className="w-4 h-4 rounded-full border-2 border-gray-600 shrink-0 mt-0.5" />
            )}
            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className={`text-sm leading-snug ${
                todo.status === "completed" ? "text-[#7f7452] line-through" :
                todo.status === "in_progress" ? "text-[#97ff8a]" :
                todo.status === "failed" ? "text-red-300" :
                "text-[#dcca8a]"
              }`}>
                {todo.title}
              </div>
              {todo.result && (
                <div className={`text-xs mt-0.5 ${
                  todo.status === "failed" ? "text-red-400/70" : "text-gray-500"
                }`}>
                  {todo.result}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Tool Steps Display ──────────────────────────────────────── */

/** Human-readable labels for tool names */
const TOOL_LABELS: Record<string, string> = {
  get_crypto_price: "Crypto Price",
  get_crypto_prices_multiple: "Crypto Prices",
  get_crypto_orderbook: "Order Book",
  get_stock_price: "Stock Price",
  get_stock_history: "Stock History",
  get_stock_info: "Stock Info",
  compare_stocks: "Compare Stocks",
  create_trigger: "Create Trigger",
  update_trigger: "Update Trigger",
  delete_trigger: "Delete Trigger",
  list_triggers: "List Triggers",
  toggle_trigger: "Toggle Trigger",
  activate_trigger: "Activate Trigger",
  deactivate_trigger: "Deactivate Trigger",
  get_trigger_status: "Trigger Status",
  send_email: "Send Email",
  read_inbox: "Read Inbox",
  read_email: "Read Email",
  search_emails: "Search Emails",
  web_search: "Web Search",
  web_fetch: "Fetch Page",
  web_scrape: "Scrape Page",
  get_trending_markets: "Trending Markets",
  get_trending_events: "Trending Events",
  search_polymarket: "Search Polymarket",
  get_market_details: "Market Details",
  send_notification: "Notification",
  request_confirmation: "Requesting Confirmation",
  create_todo_list: "Create Todo List",
  update_todo_status: "Update Todo",
  get_azure_cost_by_resource: "Cost by Resource",
  get_azure_cost_history: "Cost History",
  get_current_weather: "Current Weather",
  get_weather_forecast: "Weather Forecast",
};

/** Tool category detection for icons/colors */
function toolCategory(name: string): "crypto" | "stock" | "email" | "trigger" | "web" | "polymarket" | "notification" | "confirmation" | "todo" | "weather" | "azure" | "mcp" | "unknown" {
  if (name === "request_confirmation") return "confirmation";
  if (name === "create_todo_list" || name === "update_todo_status") return "todo";
  if (name.startsWith("get_crypto") || name === "get_crypto_orderbook") return "crypto";
  if (name.startsWith("get_stock") || name === "compare_stocks") return "stock";
  if (["send_email", "read_inbox", "read_email", "search_emails"].includes(name)) return "email";
  if (["create_trigger", "update_trigger", "delete_trigger", "list_triggers", "toggle_trigger", "activate_trigger", "deactivate_trigger", "get_trigger_status"].includes(name)) return "trigger";
  if (["web_search", "web_fetch", "web_scrape"].includes(name)) return "web";
  if (name.startsWith("get_trending") || name.startsWith("search_polymarket") || name === "get_market_details") return "polymarket";
  if (name === "send_notification") return "notification";
  if (["get_current_weather", "get_weather_forecast"].includes(name)) return "weather";
  if (name.startsWith("get_azure_cost") || name === "list_azure_subscriptions") return "azure";
  if (name.startsWith("mcp_")) return "mcp";
  return "unknown";
}

/** Color config per tool category */
const TOOL_CATEGORY_STYLES: Record<string, { bg: string; text: string; icon: string; border: string }> = {
  crypto:     { bg: "bg-yellow-900/30", text: "text-yellow-400", icon: "text-yellow-400", border: "border-yellow-800/40" },
  stock:      { bg: "bg-green-900/30",  text: "text-green-400",  icon: "text-green-400",  border: "border-green-800/40" },
  email:      { bg: "bg-sky-900/30",    text: "text-sky-400",    icon: "text-sky-400",    border: "border-sky-800/40" },
  trigger:    { bg: "bg-amber-900/30",  text: "text-amber-400",  icon: "text-amber-400",  border: "border-amber-800/40" },
  web:        { bg: "bg-indigo-900/30", text: "text-indigo-400", icon: "text-indigo-400", border: "border-indigo-800/40" },
  polymarket:    { bg: "bg-pink-900/30",   text: "text-pink-400",   icon: "text-pink-400",   border: "border-pink-800/40" },
  notification:  { bg: "bg-rose-900/30",   text: "text-rose-400",   icon: "text-rose-400",   border: "border-rose-800/40" },
  confirmation:  { bg: "bg-blue-900/30",   text: "text-blue-400",   icon: "text-blue-400",   border: "border-blue-800/40" },
  todo:          { bg: "bg-cyan-900/30",   text: "text-cyan-400",   icon: "text-cyan-400",   border: "border-cyan-800/40" },
  weather:       { bg: "bg-teal-900/30",   text: "text-teal-400",   icon: "text-teal-400",   border: "border-teal-800/40" },
  azure:         { bg: "bg-blue-900/30",   text: "text-blue-400",   icon: "text-blue-400",   border: "border-blue-800/40" },
  mcp:           { bg: "bg-purple-900/30", text: "text-purple-400", icon: "text-purple-400", border: "border-purple-800/40" },
  unknown:    { bg: "bg-gray-800/50",   text: "text-gray-400",   icon: "text-gray-400",   border: "border-gray-700/40" },
};

/** SVG icon per tool category */
function ToolCategoryIcon({ category, className = "w-3.5 h-3.5" }: { category: string; className?: string }) {
  switch (category) {
    case "crypto":
      return (
        <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      );
    case "stock":
      return (
        <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
        </svg>
      );
    case "email":
      return (
        <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
        </svg>
      );
    case "trigger":
      return (
        <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      );
    case "web":
      return (
        <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
        </svg>
      );
    case "polymarket":
      return (
        <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M3.75 3v11.25A2.25 2.25 0 006 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0118 16.5h-2.25m-7.5 0h7.5m-7.5 0l-1 3m8.5-3l1 3m0 0l.5 1.5m-.5-1.5h-9.5m0 0l-.5 1.5m.75-9l3-3 2.148 2.148A12.061 12.061 0 0116.5 7.605" />
        </svg>
      );
    case "notification":
      return (
        <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
        </svg>
      );
    case "confirmation":
      return (
        <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      );
    case "todo":
      return (
        <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
      );
    case "weather":
      return (
        <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M2.25 15a4.5 4.5 0 004.5 4.5H18a3.75 3.75 0 001.332-7.257 3 3 0 00-3.758-3.848 5.25 5.25 0 00-10.233 2.33A4.502 4.502 0 002.25 15z" />
        </svg>
      );
    case "azure":
      return (
        <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M2.25 18.75a60.07 60.07 0 0115.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 013 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 00-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 01-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 003 15h-.75M15 10.5a3 3 0 11-6 0 3 3 0 016 0zm3 0h.008v.008H18V10.5zm-12 0h.008v.008H6V10.5z" />
        </svg>
      );
    case "mcp":
      return (
        <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7" />
        </svg>
      );
    default:
      return (
        <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M11.42 15.17l-5.1-3.56a1 1 0 00-.86-.08l-2.86.94a1 1 0 01-1.28-.7l-.54-2.26a1 1 0 01.7-1.19l2.89-.78a1 1 0 00.65-.54l1.35-2.88a1 1 0 011.56-.35l2.18 1.9a1 1 0 00.88.2l2.92-.62a1 1 0 011.13.76l.54 2.26a1 1 0 01-.44 1.08l-2.44 1.56a1 1 0 00-.46.76l-.16 2.97a1 1 0 01-1.14.92l-2.26-.42a1 1 0 00-.68.12z" />
        </svg>
      );
  }
}

function toolLabel(name: string): string {
  return TOOL_LABELS[name] || name.replace(/_/g, " ").replace(/\bmcp /, "");
}

/** Format tool arguments into a brief summary */
function argsSummary(_name: string, args: Record<string, unknown>): string {
  if (args.symbol) return String(args.symbol);
  if (args.symbols) return (args.symbols as string[]).join(", ");
  if (args.to) return `to: ${String(args.to)}`;
  if (args.query) return `"${String(args.query).slice(0, 30)}${String(args.query).length > 30 ? "…" : ""}"`;
  if (args.prompt) return `"${String(args.prompt).slice(0, 30)}${String(args.prompt).length > 30 ? "…" : ""}"`;
  if (args.message) return `"${String(args.message).slice(0, 40)}${String(args.message).length > 40 ? "…" : ""}"`;
  if (args.url) return String(args.url).slice(0, 40);
  // Fallback: show first value
  const vals = Object.values(args);
  if (vals.length > 0) return String(vals[0]).slice(0, 40);
  return "";
}

function ToolStepsDisplay({ steps }: { steps: ToolStep[] }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 mb-2">
      {steps.map((step, i) => (
        <ToolStepChip key={i} step={step} />
      ))}
    </div>
  );
}

function ToolStepChip({ step }: { step: ToolStep }) {
  const [expanded, setExpanded] = useState(false);
  const cat = toolCategory(step.name);
  const styles = TOOL_CATEGORY_STYLES[cat];
  const summary = argsSummary(step.name, step.arguments);

  return (
    <div className="relative">
      <button
        onClick={() => setExpanded(!expanded)}
        className={`
          inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs
          transition-all hover:brightness-125
          ${styles.bg} ${styles.border} ${styles.text}
          ${expanded ? "ring-1 ring-white/10" : ""}
        `}
      >
        {/* Status indicator */}
        {step.status === "running" ? (
          <svg className="w-3 h-3 animate-spin flex-shrink-0" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        ) : step.status === "error" ? (
          <svg className="w-3 h-3 flex-shrink-0 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
        ) : (
          <ToolCategoryIcon category={cat} className={`w-3.5 h-3.5 flex-shrink-0 ${styles.icon}`} />
        )}

        {/* Tool label */}
        <span className="font-medium whitespace-nowrap">{toolLabel(step.name)}</span>

        {/* Brief arg summary */}
        {summary && (
          <span className="opacity-60 truncate max-w-[140px] text-[11px]">{summary}</span>
        )}

        {/* Completed check */}
        {step.status === "completed" && (
          <svg className="w-3 h-3 flex-shrink-0 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        )}

        {/* Expand indicator */}
        <svg
          className={`w-2.5 h-2.5 flex-shrink-0 opacity-40 transition-transform ${expanded ? "rotate-180" : ""}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Expanded details panel */}
      {expanded && (
        <div className={`mt-1.5 ml-1 space-y-1.5 border-l-2 pl-3 ${styles.border}`}>
          {/* Call parameters */}
          {Object.keys(step.arguments).length > 0 && (
            <div className="px-2.5 py-2 rounded-lg bg-gray-800/60 text-[11px] leading-relaxed font-mono">
              <span className="text-blue-400 font-semibold text-[10px] uppercase tracking-wide">Call</span>
              <pre className="whitespace-pre-wrap break-words text-gray-300 mt-0.5">{JSON.stringify(step.arguments, null, 2)}</pre>
            </div>
          )}
          {/* Result */}
          {step.result && (
            <div className="px-2.5 py-2 rounded-lg bg-gray-800/60 text-[11px] leading-relaxed max-h-[200px] overflow-auto font-mono">
              <span className={`font-semibold text-[10px] uppercase tracking-wide ${step.status === "error" ? "text-red-400" : "text-green-400"}`}>Result</span>
              <pre className="whitespace-pre-wrap break-words text-gray-300 mt-0.5">{JSON.stringify(step.result, null, 2)}</pre>
            </div>
          )}
          {/* Still running */}
          {step.status === "running" && !step.result && (
            <div className="px-2.5 py-1.5 text-[11px] text-blue-400/70 italic">Running…</div>
          )}
        </div>
      )}
    </div>
  );
}
