import type { Agent } from "../types/chat";

interface SidebarProps {
  agents: Agent[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  isOpen: boolean;
  onToggle: () => void;
  onOpenSettings: () => void;
}

export default function Sidebar({
  agents,
  activeId,
  onSelect,
  onNew,
  onDelete,
  isOpen,
  onToggle,
  onOpenSettings,
}: SidebarProps) {
  // Sort: active triggers first, then the rest by created_at desc
  const sortedAgents = [...agents].sort((a, b) => {
    const aActive = a.trigger?.active ? 0 : 1;
    const bActive = b.trigger?.active ? 0 : 1;
    if (aActive !== bActive) return aActive - bActive;
    return 0; // preserve existing order (already desc from API)
  });

  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-20 md:hidden"
          onClick={onToggle}
        />
      )}

      <aside
        className={`
          fixed md:static inset-y-0 left-0 z-30
          w-72 app-sidebar border-r shadow-[0_0_60px_rgba(0,0,0,0.35)]
          flex flex-col
          transform transition-transform duration-200
          ${isOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}
        `}
      >
        {/* Header */}
        <div className="border-b border-[#3dd8c5]/10 p-4">
          <div className="terminal-titlebar mb-3 rounded-sm border border-[#3dd8c5]/10 bg-[#090f13] px-3 py-2 text-[10px]">root@cronosaurus : session index</div>
          <button
            onClick={onNew}
            className="brand-button-primary w-full flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all"
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
                d="M12 4v16m8-8H4"
              />
            </svg>
            New Agent
          </button>
        </div>

        {/* Agent list */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {sortedAgents.map((agent) => {
            const hasTrigger = !!agent.trigger;
            const hasActiveTrigger = agent.trigger?.active ?? false;

            return (
              <div
                key={agent.id}
                className={`
                  group flex items-center gap-2 px-3 py-2.5 rounded-lg cursor-pointer
                  text-sm transition-colors
                  ${
                    activeId === agent.id
                      ? "bg-[#0e1922] text-[#b0f0e8] border border-teal-200/10"
                      : hasActiveTrigger
                        ? "text-[#e9dca6] hover:bg-[#2a1d0f]/85 hover:text-[#fff1ba] border border-amber-400/20 animate-[glow_2s_ease-in-out_infinite]"
                        : "text-[#78adb8] hover:bg-[#0f161b]/75 hover:text-[#c9f6ef]"
                  }
                `}
                onClick={() => onSelect(agent.id)}
              >
                {/* Icon: clock for triggered, robot for normal */}
                {hasTrigger ? (
                  <span className="relative shrink-0">
                    <svg
                      className={`w-4 h-4 ${
                        hasActiveTrigger ? "text-amber-400 animate-[spin_3s_linear_infinite]" : "text-gray-600"
                      }`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={1.5}
                        d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                    {hasActiveTrigger && (
                      <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-amber-400 rounded-full animate-pulse" />
                    )}
                  </span>
                ) : (
                  <svg
                    className="w-4 h-4 shrink-0"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.5}
                      d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714a2.25 2.25 0 00.659 1.591L19 14.5M14.25 3.104c.251.023.501.05.75.082M19 14.5l-2.47 2.47a3.375 3.375 0 01-4.06.644L12 17.5l-.47.114a3.375 3.375 0 01-4.06-.644L5 14.5m14 0V17a2.25 2.25 0 01-2.25 2.25H7.25A2.25 2.25 0 015 17v-2.5"
                    />
                  </svg>
                )}
                <span className="truncate flex-1">{agent.name}</span>
                {hasActiveTrigger && agent.trigger && (
                  <span className="flex items-center gap-1 text-[10px] text-amber-400/80 shrink-0 bg-amber-900/30 px-1.5 py-0.5 rounded-full">
                    <svg
                      className="w-2.5 h-2.5"
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
                    {agent.trigger.interval_minutes}m
                  </span>
                )}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(agent.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 transition-opacity"
                >
                  <svg
                    className="w-3.5 h-3.5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                    />
                  </svg>
                </button>
              </div>
            );
          })}

          {agents.length === 0 && (
            <p className="text-[#7d7456] text-sm text-center mt-8">
              No agents yet
            </p>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-[#3dd8c5]/10 space-y-2">
          <button
            onClick={onOpenSettings}
            className="terminal-control w-full flex items-center gap-2 px-3 py-2 rounded-lg
              text-sm text-[#78adb8] hover:bg-[#0f161b] hover:text-[#c0f6ef] transition-colors"
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
                strokeWidth={1.5}
                d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z"
              />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
              />
            </svg>
            Settings
          </button>
          <div className="terminal-titlebar justify-center mt-1 rounded-sm border border-[#3dd8c5]/10 bg-[#090f13] px-2 py-2 opacity-80">
            <img src="/logo.png" alt="Cronosaurus" className="w-4 h-4 rounded shadow-[0_0_0_1px_rgba(242,194,48,0.18)]" />
            <span className="text-[11px] uppercase tracking-[0.16em] text-[#78adb8]">Cronosaurus</span>
          </div>
        </div>
      </aside>
    </>
  );
}
