import { useState, useEffect, useCallback, useRef } from "react";
import Sidebar from "./components/Sidebar";
import ChatView from "./components/ChatView";
import ManagementPanel from "./components/ManagementPanel";
import NotificationPanel from "./components/NotificationPanel";
import OnboardingDialog from "./components/OnboardingDialog";
import { fetchUnreadCount, fetchDistributionGroups } from "./api/notification";
import { getOnboardingStatus } from "./api/settings";
import type { Agent, Message, MCPServer, ToolStep, EmailAccount, EmailAccountCreate, AppSettings, TodoItem, ToolCatalogEntry, DistributionGroup } from "./types/chat";
import {
  checkStatus,
  fetchAgents,
  fetchModels,
  createAgent,
  deleteAgent,
  updateAgent,
  fetchMessages,
  sendMessageStream,
  createAgentTrigger,
  updateAgentTrigger,
  deleteAgentTrigger,
  checkAgentBusy,
  fetchActiveDelegationAgents,
} from "./api/agent";
import {
  fetchPreferences,
  updateSelectedModel,
  updateConfirmationMode,
  fetchMCPServers,
  createMCPServer,
  updateMCPServer,
  deleteMCPServer,
  toggleMCPServer,
  updateToolLibrary,
  fetchToolCatalog,
  fetchEmailAccounts,
  createEmailAccount,
  updateEmailAccount,
  deleteEmailAccount,
  testEmailAccount,
} from "./api/user";

type AgentStreamState = {
  isStreaming: boolean;
  content: string;
  toolSteps: ToolStep[];
  todos: TodoItem[];
  images: Array<{ data: string; media_type: string }>;
};

type AgentBusyState = {
  busy: boolean;
  reason: "trigger" | "run" | null;
};

const EMPTY_STREAM_STATE: AgentStreamState = {
  isStreaming: false,
  content: "",
  toolSteps: [],
  todos: [],
  images: [],
};

const IDLE_BUSY_STATE: AgentBusyState = {
  busy: false,
  reason: null,
};

function App() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messagesCache, setMessagesCache] = useState<
    Record<string, Message[]>
  >({});
  const [streamingStates, setStreamingStates] = useState<Record<string, AgentStreamState>>({});
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [serviceReady, setServiceReady] = useState<boolean | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState("gpt-4.1-mini");
  const [confirmationMode, setConfirmationMode] = useState<"manual" | "auto" | "delayed_auto">("manual");
  const [mcpServers, setMcpServers] = useState<MCPServer[]>([]);
  const [showManagement, setShowManagement] = useState(false);
  const [managementTab, setManagementTab] = useState<"tools" | "triggers" | "email" | "mcp" | "notifications" | "appearance" | "settings">("tools");
  const streamingStatesRef = useRef<Record<string, AgentStreamState>>({});
  const abortControllersRef = useRef<Record<string, AbortController>>({});
  const toolsChangeVersion = useRef(0);
  const [emailAccounts, setEmailAccounts] = useState<EmailAccount[]>([]);
  const [toolCatalog, setToolCatalog] = useState<ToolCatalogEntry[]>([]);
  const [toolLibrary, setToolLibrary] = useState<string[]>(["crypto", "stock", "email_send", "email_read", "triggers", "web_search", "polymarket", "notifications", "azure_costs", "weather"]);
  const [showNotifications, setShowNotifications] = useState(false);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [unreadNotifications, setUnreadNotifications] = useState(0);
  const [disconnected, setDisconnected] = useState(false);
  const [distributionGroups, setDistributionGroups] = useState<DistributionGroup[]>([]);
  const [agentBusy, setAgentBusy] = useState<AgentBusyState>(IDLE_BUSY_STATE);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [onboardingChecked, setOnboardingChecked] = useState(false);
  const [delegationAgentIds, setDelegationAgentIds] = useState<string[]>([]);

  // Check onboarding status first, then load the rest
  useEffect(() => {
    const tryOnboarding = (retries = 3) => {
      getOnboardingStatus()
        .then(({ completed }) => {
          if (!completed) setShowOnboarding(true);
          setOnboardingChecked(true);
        })
        .catch(() => {
          if (retries > 0) {
            setTimeout(() => tryOnboarding(retries - 1), 2000);
          } else {
            setOnboardingChecked(true);
          }
        });
    };
    tryOnboarding();
  }, []);

  // Check service status & load agents + models + preferences on mount
  useEffect(() => {
    if (!onboardingChecked || showOnboarding) return;

    const loadData = () => {
      fetchAgents().then((agentList) => {
        setAgents(agentList);
        // Auto-create master agent if none exists
        if (!agentList.some(a => a.role === "master")) {
          createAgent({
            name: "Master Agent",
            model: "gpt-4.1-mini",
            tools: ["orchestration", "notifications", "tool_management"],
            role: "master",
          }).then((master) => {
            setAgents((prev) => [master, ...prev]);
            setActiveId(master.id);
          }).catch((e) => console.error("Failed to auto-create master agent:", e));
        }
      }).catch(() => {});
      fetchModels().then((m) => { if (m.length > 0) setModels(m); }).catch(() => {});
      fetchPreferences().then((p) => {
        if (p.selected_model) setSelectedModel(p.selected_model);
        const mode = p.confirmation_mode;
        setConfirmationMode(mode === "auto" || mode === "delayed_auto" ? mode : "manual");
        if (p.tool_library && p.tool_library.length > 0) setToolLibrary(p.tool_library);
      }).catch(() => {});
      fetchMCPServers().then(setMcpServers).catch(() => {});
      fetchEmailAccounts().then(setEmailAccounts).catch(() => {});
      fetchToolCatalog().then(setToolCatalog).catch(() => {});
      fetchDistributionGroups().then(setDistributionGroups).catch(() => {});
    };

    const tryStatus = (retries = 5) => {
      checkStatus()
        .then((s) => {
          setServiceReady(s.ready);
          if (s.ready) loadData();
          else if (retries > 0) setTimeout(() => tryStatus(retries - 1), 2000);
        })
        .catch(() => {
          if (retries > 0) setTimeout(() => tryStatus(retries - 1), 2000);
          else setServiceReady(false);
        });
    };
    tryStatus();
  }, [onboardingChecked, showOnboarding]);

  const handleOnboardingComplete = useCallback((settings: AppSettings) => {
    setShowOnboarding(false);
    // Update models from onboarding result
    if (settings.available_models?.length) setModels(settings.available_models);
    if (settings.model_deployment_name) setSelectedModel(settings.model_deployment_name);
    // Now trigger data loading by letting the useEffect run
  }, []);

  // Load messages when active agent changes
  useEffect(() => {
    if (!activeId) return;
    const cachedMessages = messagesCache[activeId];
    if (cachedMessages && cachedMessages.length > 0) return;

    setMessagesLoading(true);
    fetchMessages(activeId)
      .then((msgs) => {
        setMessagesCache((prev) => ({ ...prev, [activeId]: msgs }));
      })
      .catch(() => {})
      .finally(() => setMessagesLoading(false));
  }, [activeId]);

  const activeAgent = activeId ? agents.find((a) => a.id === activeId) ?? null : null;
  const activeStreamState = activeId ? streamingStates[activeId] ?? EMPTY_STREAM_STATE : EMPTY_STREAM_STATE;
  const activeAgentIsStreaming = activeStreamState.isStreaming;
  const streamingAgentIds = Object.entries(streamingStates)
    .filter(([, state]) => state.isStreaming)
    .map(([agentId]) => agentId);

  const setAgentStreamState = useCallback(
    (agentId: string, updater: (prev: AgentStreamState) => AgentStreamState) => {
      setStreamingStates((prev) => {
        const current = prev[agentId] ?? EMPTY_STREAM_STATE;
        const nextState = updater(current);
        const shouldKeep =
          nextState.isStreaming ||
          nextState.content.length > 0 ||
          nextState.toolSteps.length > 0 ||
          nextState.todos.length > 0 ||
          nextState.images.length > 0;
        if (!shouldKeep) {
          if (!(agentId in prev)) return prev;
          const next = { ...prev };
          delete next[agentId];
          streamingStatesRef.current = next;
          return next;
        }
        const next = { ...prev, [agentId]: nextState };
        streamingStatesRef.current = next;
        return next;
      });
    },
    []
  );

  const clearAgentStreamState = useCallback((agentId: string) => {
    setStreamingStates((prev) => {
      if (!(agentId in prev)) return prev;
      const next = { ...prev };
      delete next[agentId];
      streamingStatesRef.current = next;
      return next;
    });
  }, []);

  const stopAgentStream = useCallback(
    (agentId: string, commitPartial = true) => {
      const controller = abortControllersRef.current[agentId];
      if (controller) {
        controller.abort();
        delete abortControllersRef.current[agentId];
      }
      // Cancel any active Foundry runs so the thread isn't stuck
      import("./api/agent").then((m) => m.cancelAgentRuns(agentId)).catch(() => {});

      const state = streamingStatesRef.current[agentId];
      if (commitPartial && state) {
        const partial = state.content || "";
        if (partial || state.toolSteps.length > 0 || state.images.length > 0) {
          const assistantMsg: Message = {
            role: "assistant",
            content: partial ? `${partial}\n\n*(generation stopped)*` : "*(generation stopped)*",
            created_at: new Date().toISOString(),
          };
          if (state.toolSteps.length > 0) {
            assistantMsg.toolSteps = [...state.toolSteps];
          }
          if (state.images.length > 0) {
            assistantMsg.images = [...state.images];
          }
          setMessagesCache((prev) => ({
            ...prev,
            [agentId]: [...(prev[agentId] || []), assistantMsg],
          }));
        }
      }

      clearAgentStreamState(agentId);
    },
    [clearAgentStreamState]
  );

  const refreshAgent = useCallback(
    async (agentId: string) => {
      try {
        const updated = await import("./api/agent").then((m) => m.getAgent(agentId));
        setAgents((prev) => prev.map((a) => (a.id === agentId ? updated : a)));
      } catch {
        // ignore
      }
    },
    []
  );

  // Auto-refresh messages when the active agent has an active trigger
  useEffect(() => {
    if (!activeId || !activeAgent?.trigger?.active) return;
    if (activeAgentIsStreaming) return; // don't poll while the current agent is chatting

    const interval = setInterval(() => {
      fetchMessages(activeId)
        .then((msgs) => {
          setMessagesCache((prev) => {
            const existing = prev[activeId] || [];
            // Only update if server has MORE messages (e.g. trigger ran).
            // Never overwrite with fewer — that would discard optimistic
            // local messages from an in-flight send.
            if (msgs.length > existing.length) {
              return { ...prev, [activeId]: msgs };
            }
            return prev;
          });
        })
        .catch(() => {});
      // Also refresh agent data (trigger metadata like run_count, next_run)
      refreshAgent(activeId);
    }, 15_000); // poll every 15 seconds

    return () => clearInterval(interval);
  }, [activeId, activeAgent?.trigger?.active, activeAgentIsStreaming, refreshAgent]);

  // Poll busy status when the active agent has an active trigger
  useEffect(() => {
    if (!activeId || !activeAgent?.trigger?.active || activeAgentIsStreaming) {
      setAgentBusy(IDLE_BUSY_STATE);
      return;
    }
    let cancelled = false;
    const poll = () => {
      checkAgentBusy(activeId).then((busyState) => {
        if (!cancelled) setAgentBusy(busyState);
      });
    };
    poll(); // check immediately
    const iv = setInterval(poll, 15_000);
    return () => { cancelled = true; clearInterval(iv); };
  }, [activeId, activeAgent?.trigger?.active, activeAgentIsStreaming]);

  // Poll unread notification count + connectivity check
  useEffect(() => {
    const poll = () => {
      fetchUnreadCount()
        .then((c) => { setUnreadNotifications(c); setDisconnected(false); })
        .catch(() => setDisconnected(true));
    };
    poll();
    const interval = setInterval(poll, 15_000);
    return () => clearInterval(interval);
  }, []);

  // Poll active delegation agents for sidebar visual
  useEffect(() => {
    let cancelled = false;
    const poll = () => {
      fetchActiveDelegationAgents().then((ids) => {
        if (!cancelled) setDelegationAgentIds(ids);
      });
    };
    poll();
    const iv = setInterval(poll, 3_000);
    return () => { cancelled = true; clearInterval(iv); };
  }, []);

  const handleNewAgent = useCallback(async () => {
    try {
      const agent = await createAgent({ model: selectedModel });
      setAgents((prev) => [agent, ...prev]);
      setActiveId(agent.id);
      setMessagesCache((prev) => ({ ...prev, [agent.id]: [] }));
      setSidebarOpen(false);
    } catch (e) {
      console.error(e);
    }
  }, [selectedModel]);

  const handleUpdateManagedBy = useCallback(async (masterId: string | null) => {
    if (!activeId) return;
    try {
      const updated = await updateAgent(activeId, { managed_by: masterId } as any);
      setAgents((prev) => prev.map((a) => (a.id === activeId ? updated : a)));
    } catch (e) {
      console.error(e);
    }
  }, [activeId]);

  const handleNewAgentWithPrompt = useCallback(async (_prompt: string, tools?: string[]) => {
    try {
      const agent = await createAgent({ model: selectedModel, ...(tools ? { tools } : {}) });
      setAgents((prev) => [agent, ...prev]);
      setActiveId(agent.id);
      setMessagesCache((prev) => ({ ...prev, [agent.id]: [] }));
      setSidebarOpen(false);
      // The prompt is filled by ChatView via pendingPrompt state
    } catch (e) {
      console.error(e);
    }
  }, [selectedModel]);

  const handleSelect = useCallback((id: string) => {
    setActiveId(id);
    setSidebarOpen(false);
  }, []);

  const handleDelete = useCallback(
    async (id: string) => {
      // Prevent deleting master agent
      const agent = agents.find(a => a.id === id);
      if (agent?.role === "master") return;

      stopAgentStream(id, false);
      // Optimistic: remove from UI immediately
      const prevAgents = agents;
      setAgents((prev) => prev.filter((a) => a.id !== id));
      if (activeId === id) setActiveId(null);
      setMessagesCache((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      try {
        await deleteAgent(id);
      } catch (e) {
        // Revert on failure
        setAgents(prevAgents);
        console.error(e);
      }
    },
    [activeId, agents, stopAgentStream]
  );

  const handleStop = useCallback(() => {
    if (!activeId) return;
    stopAgentStream(activeId, true);
  }, [activeId, stopAgentStream]);

  const handleSend = useCallback(
    async (content: string, images?: Array<{ data: string; media_type: string }>) => {
      if (!activeId) return;
      const agentId = activeId;

      // If this agent is already streaming, stop its current response first.
      if (streamingStatesRef.current[agentId]?.isStreaming) {
        stopAgentStream(agentId, true);
      }

      const userMsg: Message = { role: "user", content, created_at: new Date().toISOString() };
      if (images && images.length > 0) {
        userMsg.images = images;
      }
      setMessagesCache((prev) => ({
        ...prev,
        [agentId]: [...(prev[agentId] || []), userMsg],
      }));

      setAgentStreamState(agentId, () => ({
        isStreaming: true,
        content: "",
        toolSteps: [],
        todos: [],
        images: [],
      }));

      const controller = new AbortController();
      abortControllersRef.current[agentId] = controller;
      const isCurrentRun = () => abortControllersRef.current[agentId] === controller && !controller.signal.aborted;

      // If the thread is busy (trigger running), wait for it to finish
      // before sending the user message. Show a "waiting" delta.
      try {
        let busyState = await checkAgentBusy(agentId);
        if (busyState.busy) {
          setAgentStreamState(agentId, (prev) => ({
            ...prev,
            isStreaming: true,
            content: busyState.reason === "trigger"
              ? "Waiting for the running trigger to finish...\n"
              : "Waiting for the current run to finish...\n",
          }));
          const waitStart = Date.now();
          const MAX_WAIT = 60_000; // 60 seconds max
          while (busyState.busy && Date.now() - waitStart < MAX_WAIT) {
            await new Promise((r) => setTimeout(r, 2_000));
            if (controller.signal.aborted) break;
            busyState = await checkAgentBusy(agentId);
          }
          if (!isCurrentRun()) return;
          setAgentStreamState(agentId, (prev) => ({ ...prev, isStreaming: true, content: "" }));
          if (controller.signal.aborted) {
            return;
          }
        }
      } catch {
        // If busy check fails, proceed anyway — backend will handle it
      }

      try {
        await sendMessageStream(
          agentId,
          content,
          (delta) => {
            if (!isCurrentRun()) return;
            setAgentStreamState(agentId, (prev) => ({
              ...prev,
              isStreaming: true,
              content: prev.content + delta,
            }));
          },
          (fullText) => {
            if (!isCurrentRun()) return;
            const state = streamingStatesRef.current[agentId] ?? EMPTY_STREAM_STATE;
            const assistantMsg: Message = {
              role: "assistant",
              content: fullText || state.content,
              created_at: new Date().toISOString(),
            };
            if (state.toolSteps.length > 0) {
              assistantMsg.toolSteps = [...state.toolSteps];
            }
            if (state.images.length > 0) {
              assistantMsg.images = [...state.images];
            }
            setMessagesCache((prev) => ({
              ...prev,
              [agentId]: [...(prev[agentId] || []), assistantMsg],
            }));
            delete abortControllersRef.current[agentId];
            clearAgentStreamState(agentId);
            // Refresh agent data (trigger may have been modified by the agent)
            refreshAgent(agentId);
            // Delayed refresh to pick up background auto-naming
            setTimeout(() => refreshAgent(agentId), 3000);
          },
          (error) => {
            if (!isCurrentRun()) return;
            console.error("Stream error:", error);
            const errorMsg: Message = {
              role: "assistant",
              content: `Error: ${error}`,
              created_at: new Date().toISOString(),
            };
            setMessagesCache((prev) => ({
              ...prev,
              [agentId]: [...(prev[agentId] || []), errorMsg],
            }));
            delete abortControllersRef.current[agentId];
            clearAgentStreamState(agentId);
          },
          controller.signal,
          () => refreshAgent(agentId),
          (step: ToolStep) => {
            if (!isCurrentRun()) return;
            setAgentStreamState(agentId, (prev) => ({
              ...prev,
              isStreaming: true,
              toolSteps: [...prev.toolSteps, step],
            }));
          },
          (name: string, result: Record<string, unknown>) => {
            if (!isCurrentRun()) return;
            setAgentStreamState(agentId, (prev) => ({
              ...prev,
              isStreaming: true,
              toolSteps: prev.toolSteps.map((s) =>
                s.name === name && s.status === "running"
                  ? { ...s, result, status: result.success === false ? "error" : ("completed" as const) }
                  : s
              ),
              todos:
                (name === "create_todo_list" || name === "update_todo_status") && Array.isArray(result.todos)
                  ? (result.todos as TodoItem[])
                  : prev.todos,
            }));
            // Refresh sidebar when master creates a new agent
            if (name === "create_agent" && result.success) {
              fetchAgents().then(setAgents).catch(() => {});
            }
          },
          // onNameUpdate — auto-generated agent name
          (newName: string) => {
            if (!isCurrentRun()) return;
            setAgents((prev) =>
              prev.map((a) => (a.id === agentId ? { ...a, name: newName } : a))
            );
          },
          images,
          // onImage — tool-captured image (e.g. Twitch)
          (img: { data: string; media_type: string }) => {
            if (!isCurrentRun()) return;
            setAgentStreamState(agentId, (prev) => ({
              ...prev,
              isStreaming: true,
              images: [...prev.images, img],
            }));
          },
        );
      } catch {
        if (!isCurrentRun()) return;
        delete abortControllersRef.current[agentId];
        clearAgentStreamState(agentId);
      }
    },
    [activeId, clearAgentStreamState, refreshAgent, setAgentStreamState, stopAgentStream]
  );

  // When switching agents, update selected model to match the agent
  useEffect(() => {
    if (!activeAgent) return;
    if (activeAgent.model) {
      setSelectedModel(activeAgent.model);
    }
  }, [activeAgent]);

  const handleModelChange = useCallback(
    async (model: string) => {
      setSelectedModel(model);
      updateSelectedModel(model).catch(() => {});
      if (activeId) {
        try {
          const updated = await updateAgent(activeId, { model });
          setAgents((prev) =>
            prev.map((a) => (a.id === updated.id ? updated : a))
          );
        } catch {
          // ignore
        }
      }
    },
    [activeId]
  );

  const handleConfirmationModeChange = useCallback(
    async (mode: "manual" | "auto" | "delayed_auto") => {
      const previous = confirmationMode;
      setConfirmationMode(mode);
      try {
        await updateConfirmationMode(mode);
      } catch {
        setConfirmationMode(previous);
      }
    },
    [confirmationMode]
  );

  const handleRenameAgent = useCallback(
    async (name: string) => {
      if (!activeId) return;
      try {
        const updated = await updateAgent(activeId, { name });
        setAgents((prev) =>
          prev.map((a) => (a.id === updated.id ? updated : a))
        );
      } catch {
        // ignore
      }
    },
    [activeId]
  );

  const handleToolsChange = useCallback(
    async (tools: string[]) => {
      if (!activeId) return;
      // Bump version — only the latest inflight request should apply its result
      const version = ++toolsChangeVersion.current;
      // Optimistic update
      setAgents((prev) =>
        prev.map((a) => (a.id === activeId ? { ...a, tools } : a))
      );
      try {
        const updated = await updateAgent(activeId, { tools });
        // Only apply server response if no newer toggle has happened
        if (toolsChangeVersion.current === version) {
          setAgents((prev) =>
            prev.map((a) => (a.id === updated.id ? updated : a))
          );
        }
      } catch {
        // Revert on failure only if still the latest version
        if (toolsChangeVersion.current === version) {
          refreshAgent(activeId);
        }
      }
    },
    [activeId, refreshAgent]
  );

  const handleEmailAccountChange = useCallback(
    async (accountId: string | null) => {
      if (!activeId) return;
      setAgents((prev) =>
        prev.map((a) => (a.id === activeId ? { ...a, email_account_id: accountId } : a))
      );
      try {
        const updated = await updateAgent(activeId, { email_account_id: accountId });
        setAgents((prev) =>
          prev.map((a) => (a.id === updated.id ? updated : a))
        );
      } catch {
        refreshAgent(activeId);
      }
    },
    [activeId, refreshAgent]
  );

  const handleCustomInstructionsChange = useCallback(
    async (instructions: string) => {
      if (!activeId) return;
      setAgents((prev) =>
        prev.map((a) => (a.id === activeId ? { ...a, custom_instructions: instructions } : a))
      );
      try {
        const updated = await updateAgent(activeId, { custom_instructions: instructions });
        setAgents((prev) =>
          prev.map((a) => (a.id === updated.id ? updated : a))
        );
      } catch {
        refreshAgent(activeId);
      }
    },
    [activeId, refreshAgent]
  );

  const handleNotificationGroupChange = useCallback(
    async (groupId: string | null) => {
      if (!activeId) return;
      setAgents((prev) =>
        prev.map((a) => (a.id === activeId ? { ...a, notification_group_id: groupId } : a))
      );
      try {
        const updated = await updateAgent(activeId, { notification_group_id: groupId });
        setAgents((prev) =>
          prev.map((a) => (a.id === updated.id ? updated : a))
        );
      } catch {
        refreshAgent(activeId);
      }
    },
    [activeId, refreshAgent]
  );

  // --- MCP server handlers ---
  const handleAddMCP = useCallback(async (server: Omit<MCPServer, "id">) => {
    try {
      const created = await createMCPServer(server);
      setMcpServers((prev) => [...prev, created]);
      // Auto-add active MCP server to tool library
      if (created.active) {
        const newLib = await updateToolLibrary(`mcp:${created.id}`, "add");
        setToolLibrary(newLib);
      }
    } catch (e) {
      console.error("Failed to add MCP server", e);
    }
  }, []);

  const handleDeleteMCP = useCallback(async (id: string) => {
    try {
      await deleteMCPServer(id);
      setMcpServers((prev) => prev.filter((s) => s.id !== id));
      // Remove from tool library
      const newLib = await updateToolLibrary(`mcp:${id}`, "remove");
      setToolLibrary(newLib);
    } catch (e) {
      console.error("Failed to delete MCP server", e);
    }
  }, []);

  const handleToggleMCP = useCallback(async (id: string, active: boolean) => {
    try {
      const updated = await toggleMCPServer(id, active);
      setMcpServers((prev) => prev.map((s) => (s.id === id ? updated : s)));
      // Auto-add/remove from tool library
      const newLib = await updateToolLibrary(`mcp:${id}`, active ? "add" : "remove");
      setToolLibrary(newLib);
    } catch (e) {
      console.error("Failed to toggle MCP server", e);
    }
  }, []);

  const handleUpdateMCP = useCallback(async (id: string, data: Partial<Omit<MCPServer, "id">>) => {
    try {
      const updated = await updateMCPServer(id, data);
      setMcpServers((prev) => prev.map((s) => (s.id === id ? updated : s)));
    } catch (e) {
      console.error("Failed to update MCP server", e);
    }
  }, []);

  // --- Trigger handlers (per-agent) ---
  const handleCreateTrigger = useCallback(
    async (data: {
      type?: string;
      interval_minutes?: number;
      prompt: string;
      description?: string;
      filter_from?: string;
      filter_subject?: string;
    }) => {
      if (!activeId) return;
      try {
        const updatedAgent = await createAgentTrigger(activeId, data);
        setAgents((prev) => prev.map((a) => (a.id === updatedAgent.id ? updatedAgent : a)));
      } catch (e) {
        console.error("Failed to create trigger", e);
      }
    },
    [activeId]
  );

  const handleUpdateTrigger = useCallback(
    async (data: Partial<{
      interval_minutes: number;
      prompt: string;
      description: string;
      filter_from: string;
      filter_subject: string;
    }>) => {
      if (!activeId) return;
      try {
        const updatedAgent = await updateAgentTrigger(activeId, data);
        setAgents((prev) => prev.map((a) => (a.id === updatedAgent.id ? updatedAgent : a)));
      } catch (e) {
        console.error("Failed to update trigger", e);
      }
    },
    [activeId]
  );

  const handleDeleteTrigger = useCallback(async () => {
    if (!activeId) return;
    try {
      await deleteAgentTrigger(activeId);
      setAgents((prev) =>
        prev.map((a) => (a.id === activeId ? { ...a, trigger: null } : a))
      );
    } catch (e) {
      console.error("Failed to delete trigger", e);
    }
  }, [activeId]);

  const handleToggleTrigger = useCallback(
    async (active: boolean) => {
      if (!activeId) return;
      try {
        const updatedAgent = await updateAgentTrigger(activeId, { active });
        setAgents((prev) => prev.map((a) => (a.id === updatedAgent.id ? updatedAgent : a)));
      } catch (e) {
        console.error("Failed to toggle trigger", e);
      }
    },
    [activeId]
  );

  // --- Email account handlers ---
  const handleAddEmail = useCallback(async (data: EmailAccountCreate) => {
    try {
      const saved = await createEmailAccount(data);
      setEmailAccounts((prev) => {
        // If the new account is default, unset others
        if (saved.is_default) {
          return [...prev.map((a) => ({ ...a, is_default: false })), saved];
        }
        return [...prev, saved];
      });
    } catch (e) {
      console.error("Failed to add email account", e);
    }
  }, []);

  const handleUpdateEmail = useCallback(async (id: string, data: Partial<EmailAccountCreate>) => {
    try {
      const updated = await updateEmailAccount(id, data);
      setEmailAccounts((prev) => {
        let list = prev.map((a) => (a.id === id ? updated : a));
        // If updated account became default, unset others
        if (updated.is_default) {
          list = list.map((a) => (a.id === id ? a : { ...a, is_default: false }));
        }
        return list;
      });
    } catch (e) {
      console.error("Failed to update email account", e);
    }
  }, []);

  const handleDeleteEmail = useCallback(async (id: string) => {
    try {
      await deleteEmailAccount(id);
      setEmailAccounts((prev) => {
        const remaining = prev.filter((a) => a.id !== id);
        // If we deleted the default, make the first one default
        if (remaining.length > 0 && !remaining.some((a) => a.is_default)) {
          remaining[0] = { ...remaining[0], is_default: true };
        }
        return remaining;
      });
    } catch (e) {
      console.error("Failed to delete email account", e);
    }
  }, []);

  const handleTestEmail = useCallback(async (id: string) => {
    return testEmailAccount(id);
  }, []);

  const currentMessages = activeId ? messagesCache[activeId] || [] : [];

  return (
    <div className="app-shell flex h-screen text-[#f6efc9]">
      {/* Disconnection banner */}
      {disconnected && (
        <div className="fixed top-0 left-0 right-0 z-[100] flex items-center justify-center gap-2 px-4 py-2 bg-red-900/90 border-b border-red-700/50 text-red-200 text-xs backdrop-blur-sm">
          <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
          </svg>
          <span>Connection to backend lost — retrying automatically</span>
        </div>
      )}
      {showOnboarding && (
        <OnboardingDialog onComplete={handleOnboardingComplete} />
      )}
      <Sidebar
        agents={agents}
        activeId={activeId}
        streamingAgentIds={streamingAgentIds}
        delegationAgentIds={delegationAgentIds}
        onSelect={handleSelect}
        onNew={handleNewAgent}
        onDelete={handleDelete}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
        onOpenSettings={() => { setManagementTab("settings"); setShowManagement(true); }}
      />
      <ChatView
        messages={currentMessages}
        messagesLoading={messagesLoading}
        streamingContent={activeStreamState.content}
        streamingToolSteps={activeStreamState.toolSteps}
        streamingTodos={activeStreamState.todos}
        streamingImages={activeStreamState.images}
        isStreaming={activeAgentIsStreaming}
        onSend={handleSend}
        onStop={handleStop}
        onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        activeAgent={activeAgent}
        serviceReady={serviceReady}
        onNewAgent={handleNewAgent}
        models={models}
        selectedModel={selectedModel}
        confirmationMode={confirmationMode}
        onModelChange={handleModelChange}
        onConfirmationModeChange={handleConfirmationModeChange}
        onOpenManagement={(tab) => { setManagementTab(tab as "tools" | "triggers" | "email" | "mcp" | "notifications" | "appearance" | "settings"); setShowManagement(true); }}
        onRenameAgent={handleRenameAgent}
        onToolsChange={handleToolsChange}
        toolLibrary={toolLibrary}
        mcpServers={mcpServers}
        agentBusy={agentBusy.busy}
        agentBusyReason={agentBusy.reason}
        emailAccounts={emailAccounts}
        onEmailAccountChange={handleEmailAccountChange}
        onNewAgentWithPrompt={handleNewAgentWithPrompt}
        toolCatalog={toolCatalog}
        onCustomInstructionsChange={handleCustomInstructionsChange}
        distributionGroups={distributionGroups}
        onNotificationGroupChange={handleNotificationGroupChange}
        onOpenNotifications={() => setShowNotifications(true)}
        unreadNotifications={unreadNotifications}
        allAgents={agents}
        onUpdateManagedBy={handleUpdateManagedBy}
      />
      {showManagement && (
        <ManagementPanel
          defaultTab={managementTab}
          onClose={() => { setShowManagement(false); fetchDistributionGroups().then(setDistributionGroups).catch(() => {}); }}
          emailAccounts={emailAccounts}
          onToolLibraryChange={(lib) => setToolLibrary(lib)}
          agents={agents}
          activeAgent={activeAgent}
          onSelectAgent={(id) => { setActiveId(id); }}
          onAgentsChange={setAgents}
          onCreateTrigger={handleCreateTrigger}
          onUpdateTrigger={handleUpdateTrigger}
          onToggleTrigger={handleToggleTrigger}
          onDeleteTrigger={handleDeleteTrigger}
          onAddEmail={handleAddEmail}
          onUpdateEmail={handleUpdateEmail}
          onDeleteEmail={handleDeleteEmail}
          onTestEmail={handleTestEmail}
          mcpServers={mcpServers}
          onAddMCP={handleAddMCP}
          onDeleteMCP={handleDeleteMCP}
          onToggleMCP={handleToggleMCP}
          onUpdateMCP={handleUpdateMCP}
        />
      )}
      <NotificationPanel
        isOpen={showNotifications}
        onClose={() => {
          setShowNotifications(false);
          fetchUnreadCount().then(setUnreadNotifications).catch(() => {});
        }}
      />
    </div>
  );
}

export default App;
