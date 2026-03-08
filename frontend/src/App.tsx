import { useState, useEffect, useCallback, useRef } from "react";
import Sidebar from "./components/Sidebar";
import ChatView from "./components/ChatView";
import ManagementPanel from "./components/ManagementPanel";
import NotificationPanel from "./components/NotificationPanel";
import OnboardingDialog from "./components/OnboardingDialog";
import { fetchUnreadCount } from "./api/notification";
import { getOnboardingStatus } from "./api/settings";
import type { Agent, Message, MCPServer, ToolStep, EmailAccount, EmailAccountCreate, AppSettings, TodoItem, ToolCatalogEntry } from "./types/chat";
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
} from "./api/agent";
import {
  fetchPreferences,
  updateSelectedModel,
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

function App() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messagesCache, setMessagesCache] = useState<
    Record<string, Message[]>
  >({});
  const [streamingContent, setStreamingContent] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [serviceReady, setServiceReady] = useState<boolean | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState("gpt-4.1-mini");
  const [mcpServers, setMcpServers] = useState<MCPServer[]>([]);
  const [showManagement, setShowManagement] = useState(false);
  const [managementTab, setManagementTab] = useState<"tools" | "triggers" | "email" | "mcp" | "settings">("tools");
  const [streamingToolSteps, setStreamingToolSteps] = useState<ToolStep[]>([]);
  const streamingToolStepsRef = useRef<ToolStep[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const toolsChangeVersion = useRef(0);
  const [emailAccounts, setEmailAccounts] = useState<EmailAccount[]>([]);
  const [toolCatalog, setToolCatalog] = useState<ToolCatalogEntry[]>([]);
  const [toolLibrary, setToolLibrary] = useState<string[]>(["crypto", "stock", "email_send", "email_read", "triggers", "web_search", "polymarket", "notifications", "azure_costs", "weather"]);
  const [showNotifications, setShowNotifications] = useState(false);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [unreadNotifications, setUnreadNotifications] = useState(0);
  const [agentBusy, setAgentBusy] = useState(false);
  const [streamingAgentId, setStreamingAgentId] = useState<string | null>(null);
  const [streamingTodos, setStreamingTodos] = useState<TodoItem[]>([]);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [onboardingChecked, setOnboardingChecked] = useState(false);

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
      fetchAgents().then(setAgents).catch(() => {});
      fetchModels().then((m) => { if (m.length > 0) setModels(m); }).catch(() => {});
      fetchPreferences().then((p) => {
        if (p.selected_model) setSelectedModel(p.selected_model);
        if (p.tool_library && p.tool_library.length > 0) setToolLibrary(p.tool_library);
      }).catch(() => {});
      fetchMCPServers().then(setMcpServers).catch(() => {});
      fetchEmailAccounts().then(setEmailAccounts).catch(() => {});
      fetchToolCatalog().then(setToolCatalog).catch(() => {});
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
    if (isStreaming) return; // don't poll while the user is chatting

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
  }, [activeId, activeAgent?.trigger?.active, isStreaming, refreshAgent]);

  // Poll busy status when the active agent has an active trigger
  useEffect(() => {
    if (!activeId || !activeAgent?.trigger?.active) {
      setAgentBusy(false);
      return;
    }
    let cancelled = false;
    const poll = () => {
      checkAgentBusy(activeId).then((busy) => {
        if (!cancelled) setAgentBusy(busy);
      });
    };
    poll(); // check immediately
    const iv = setInterval(poll, 5_000);
    return () => { cancelled = true; clearInterval(iv); };
  }, [activeId, activeAgent?.trigger?.active]);

  // Poll unread notification count
  useEffect(() => {
    fetchUnreadCount().then(setUnreadNotifications).catch(() => {});
    const interval = setInterval(() => {
      fetchUnreadCount().then(setUnreadNotifications).catch(() => {});
    }, 15_000);
    return () => clearInterval(interval);
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

  const handleNewAgentWithPrompt = useCallback(async (_prompt: string) => {
    try {
      const agent = await createAgent({ model: selectedModel });
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
    [activeId, agents]
  );

  const handleStop = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    // Commit whatever has streamed so far as an assistant message
    const agentId = activeId;
    if (agentId) {
      const partial = streamingContent || "";
      const steps = streamingToolStepsRef.current;
      if (partial || steps.length > 0) {
        const assistantMsg: Message = {
          role: "assistant",
          content: partial + "\n\n*(generation stopped)*",
          created_at: new Date().toISOString(),
        };
        if (steps.length > 0) {
          assistantMsg.toolSteps = [...steps];
        }
        setMessagesCache((prev) => ({
          ...prev,
          [agentId]: [...(prev[agentId] || []), assistantMsg],
        }));
      }
    }
    setStreamingContent("");
    setStreamingToolSteps([]);
    streamingToolStepsRef.current = [];
    setIsStreaming(false);
    setStreamingAgentId(null);
  }, [activeId, streamingContent]);

  const handleSend = useCallback(
    async (content: string, images?: Array<{ data: string; media_type: string }>) => {
      if (!activeId) return;
      // If already streaming, abort the current one first
      if (isStreaming) {
        handleStop();
      }

      const userMsg: Message = { role: "user", content, created_at: new Date().toISOString() };
      if (images && images.length > 0) {
        userMsg.images = images;
      }
      setMessagesCache((prev) => ({
        ...prev,
        [activeId]: [...(prev[activeId] || []), userMsg],
      }));
      setIsStreaming(true);
      setStreamingAgentId(activeId);
      setStreamingContent("");
      setStreamingToolSteps([]);
      setStreamingTodos([]);

      const controller = new AbortController();
      abortRef.current = controller;
      const agentId = activeId;

      // If the thread is busy (trigger running), wait for it to finish
      // before sending the user message. Show a "waiting" delta.
      try {
        let busy = await checkAgentBusy(agentId);
        if (busy) {
          setStreamingContent("Waiting for a running trigger to finish...\n");
          const waitStart = Date.now();
          const MAX_WAIT = 60_000; // 60 seconds max
          while (busy && Date.now() - waitStart < MAX_WAIT) {
            await new Promise((r) => setTimeout(r, 2_000));
            if (controller.signal.aborted) break;
            busy = await checkAgentBusy(agentId);
          }
          setStreamingContent("");
          if (controller.signal.aborted) {
            setIsStreaming(false);
            setStreamingAgentId(null);
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
            setStreamingContent((prev) => prev + delta);
          },
          (fullText) => {
            const assistantMsg: Message = {
              role: "assistant",
              content: fullText,
              created_at: new Date().toISOString(),
            };
            const steps = streamingToolStepsRef.current;
            if (steps.length > 0) {
              assistantMsg.toolSteps = [...steps];
            }
            setMessagesCache((prev) => ({
              ...prev,
              [agentId]: [...(prev[agentId] || []), assistantMsg],
            }));
            setStreamingToolSteps([]);
            streamingToolStepsRef.current = [];
            setStreamingContent("");
            setIsStreaming(false);
            setStreamingAgentId(null);
            setStreamingTodos([]);
            // Refresh agent data (trigger may have been modified by the agent)
            refreshAgent(agentId);
            // Delayed refresh to pick up background auto-naming
            setTimeout(() => refreshAgent(agentId), 3000);
          },
          (error) => {
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
            setStreamingContent("");
            setIsStreaming(false);
            setStreamingAgentId(null);
            setStreamingToolSteps([]);
            streamingToolStepsRef.current = [];
            setStreamingTodos([]);
          },
          controller.signal,
          () => refreshAgent(agentId),
          (step: ToolStep) => {
            streamingToolStepsRef.current = [...streamingToolStepsRef.current, step];
            setStreamingToolSteps((prev) => [...prev, step]);
          },
          (name: string, result: Record<string, unknown>) => {
            streamingToolStepsRef.current = streamingToolStepsRef.current.map((s) =>
              s.name === name && s.status === "running"
                ? { ...s, result, status: result.success === false ? "error" : ("completed" as const) }
                : s
            );
            setStreamingToolSteps((prev) =>
              prev.map((s) =>
                s.name === name && s.status === "running"
                  ? { ...s, result, status: result.success === false ? "error" : ("completed" as const) }
                  : s
              )
            );
            // Track todo list updates
            if ((name === "create_todo_list" || name === "update_todo_status") && Array.isArray(result.todos)) {
              setStreamingTodos(result.todos as TodoItem[]);
            }
          },
          // onNameUpdate — auto-generated agent name
          (newName: string) => {
            setAgents((prev) =>
              prev.map((a) => (a.id === agentId ? { ...a, name: newName } : a))
            );
          },
          images,
        );
      } catch {
        setIsStreaming(false);
        setStreamingAgentId(null);
        setStreamingContent("");
        setStreamingToolSteps([]);
        streamingToolStepsRef.current = [];
        setStreamingTodos([]);
      }
    },
    [activeId, isStreaming, handleStop, refreshAgent]
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
      {showOnboarding && (
        <OnboardingDialog onComplete={handleOnboardingComplete} />
      )}
      <Sidebar
        agents={agents}
        activeId={activeId}
        onSelect={handleSelect}
        onNew={handleNewAgent}
        onDelete={handleDelete}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
        onOpenSettings={() => { setManagementTab("settings"); setShowManagement(true); }}
        onOpenNotifications={() => setShowNotifications(true)}
        unreadNotifications={unreadNotifications}
      />
      <ChatView
        messages={currentMessages}
        messagesLoading={messagesLoading}
        streamingContent={activeId === streamingAgentId ? streamingContent : ""}
        streamingToolSteps={activeId === streamingAgentId ? streamingToolSteps : []}
        streamingTodos={activeId === streamingAgentId ? streamingTodos : []}
        isStreaming={isStreaming && activeId === streamingAgentId}
        onSend={handleSend}
        onStop={handleStop}
        onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        activeAgent={activeAgent}
        serviceReady={serviceReady}
        onNewAgent={handleNewAgent}
        models={models}
        selectedModel={selectedModel}
        onModelChange={handleModelChange}
        onOpenManagement={(tab) => { setManagementTab(tab as "tools" | "triggers" | "email" | "mcp" | "settings"); setShowManagement(true); }}
        onRenameAgent={handleRenameAgent}
        onToolsChange={handleToolsChange}
        toolLibrary={toolLibrary}
        mcpServers={mcpServers}
        agentBusy={agentBusy}
        emailAccounts={emailAccounts}
        onEmailAccountChange={handleEmailAccountChange}
        onNewAgentWithPrompt={handleNewAgentWithPrompt}
        toolCatalog={toolCatalog}
      />
      {showManagement && (
        <ManagementPanel
          defaultTab={managementTab}
          onClose={() => setShowManagement(false)}
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
