import { useState } from "react";
import { completeOnboarding, testFoundryConnection, testCosmosConnection, fetchDeployments } from "../api/settings";
import type { FoundryDeployment } from "../api/settings";
import type { AppSettings } from "../types/chat";

const ALL_MODELS = [
  "gpt-4.1",
  "gpt-4.1-mini",
  "gpt-4.1-nano",
  "gpt-4o",
  "gpt-5",
  "gpt-5-mini",
  "gpt-5-nano",
  "model-router",
];

interface OnboardingDialogProps {
  onComplete: (settings: AppSettings) => void;
}

export default function OnboardingDialog({ onComplete }: OnboardingDialogProps) {
  const [step, setStep] = useState(0);

  // Foundry
  const [projectEndpoint, setProjectEndpoint] = useState("");
  const [modelDeployment, setModelDeployment] = useState("gpt-4.1-mini");
  const [selectedModels, setSelectedModels] = useState<string[]>([
    "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-4o",
  ]);

  // Cosmos DB
  const [cosmosUrl, setCosmosUrl] = useState("");
  const [cosmosKey, setCosmosKey] = useState("");
  const [cosmosDb, setCosmosDb] = useState("cronosaurus");

  // Tool config
  const [configureEmail, setConfigureEmail] = useState(false);
  const [configureCosmos, setConfigureCosmos] = useState(false);

  // Test state
  const [foundryTest, setFoundryTest] = useState<{ status: "idle" | "testing" | "success" | "error"; message: string }>({ status: "idle", message: "" });
  const [cosmosTest, setCosmosTest] = useState<{ status: "idle" | "testing" | "success" | "error"; message: string }>({ status: "idle", message: "" });

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [deploymentsLoading, setDeploymentsLoading] = useState(false);
  const [deploymentsError, setDeploymentsError] = useState("");
  const [foundryDeployments, setFoundryDeployments] = useState<FoundryDeployment[]>([]);

  const toggleModel = (model: string) => {
    setSelectedModels((prev) =>
      prev.includes(model) ? prev.filter((m) => m !== model) : [...prev, model]
    );
  };

  const handleTestFoundry = async () => {
    setFoundryTest({ status: "testing", message: "Testing connection..." });
    try {
      const result = await testFoundryConnection();
      setFoundryTest({
        status: result.success ? "success" : "error",
        message: result.message || result.error || "",
      });
    } catch {
      setFoundryTest({ status: "error", message: "Connection test failed" });
    }
  };

  const handleLoadDeployments = async () => {
    setDeploymentsLoading(true);
    setDeploymentsError("");
    try {
      const r = await fetchDeployments();
      if (r.success) {
        setFoundryDeployments(r.deployments);
        const names = r.deployments.map((d) => d.name);
        setSelectedModels((prev) => {
          const merged = new Set([...prev, ...names]);
          return Array.from(merged);
        });
      } else {
        setDeploymentsError(r.error || "Failed to load deployments");
      }
    } catch {
      setDeploymentsError("Failed to load deployments");
    } finally {
      setDeploymentsLoading(false);
    }
  };

  const handleTestCosmos = async () => {
    setCosmosTest({ status: "testing", message: "Testing connection..." });
    try {
      const result = await testCosmosConnection();
      setCosmosTest({
        status: result.success ? "success" : "error",
        message: result.message || result.error || "",
      });
    } catch {
      setCosmosTest({ status: "error", message: "Connection test failed" });
    }
  };

  const handleFinish = async () => {
    setSaving(true);
    setError("");
    try {
      const result = await completeOnboarding({
        project_endpoint: projectEndpoint,
        model_deployment_name: modelDeployment,
        available_models: selectedModels.length > 0 ? selectedModels : ["gpt-4.1-mini"],
        cosmos_url: cosmosUrl,
        cosmos_key: cosmosKey,
        cosmos_db: cosmosDb,
        configure_email: configureEmail,
        configure_cosmos: configureCosmos,
      });
      onComplete(result);
    } catch {
      setError("Failed to save settings. Please try again.");
      setSaving(false);
    }
  };

  const steps = [
    { title: "Welcome", icon: "👋" },
    { title: "AI Foundry", icon: "🤖" },
    { title: "Models", icon: "🧠" },
    { title: "Cosmos DB", icon: "🗄️" },
    { title: "Tools", icon: "🔧" },
    { title: "Ready", icon: "🚀" },
  ];

  const canProceed = () => {
    switch (step) {
      case 0: return true;
      case 1: return projectEndpoint.trim().length > 0;
      case 2: return selectedModels.length > 0;
      case 3: return true; // Cosmos is optional at onboarding
      case 4: return true;
      case 5: return true;
      default: return true;
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm">
      <div className="app-modal w-full max-w-2xl mx-4 overflow-hidden rounded-2xl shadow-2xl">
        <div className="terminal-titlebar px-6">cronosaurus :: setup wizard</div>
        {/* Header progress */}
        <div className="px-6 pt-5 pb-4">
          <div className="flex items-center gap-2 mb-4">
            {steps.map((s, i) => (
              <div key={i} className="flex items-center gap-2">
                <div
                  className={`w-8 h-8 flex items-center justify-center text-xs font-medium transition-colors border ${
                    i < step ? "bg-[#122215] border-[#97ff8a]/40 text-[#97ff8a]" :
                    i === step ? "bg-[#3dd8c5] border-[#3dd8c5] text-[#071210]" :
                    "bg-[#16120c] border-[#1d4c5f] text-[#597f8b]"
                  }`}
                >
                  {i < step ? "✓" : s.icon}
                </div>
                {i < steps.length - 1 && (
                  <div className={`w-6 h-0.5 ${i < step ? "bg-[#97ff8a]" : "bg-[#3a3020]"}`} />
                )}
              </div>
            ))}
          </div>
          <h2 className="text-xl font-semibold text-[#b0f0e8] uppercase tracking-[0.08em]">{steps[step].title}</h2>
        </div>

        {/* Step content */}
        <div className="px-6 pb-6 min-h-[320px]">
          {step === 0 && (
            <div className="space-y-4">
              <div className="brand-display text-4xl mb-2 text-[#b0f0e8]">Welcome to Cronosaurus! 👋</div>
              <p className="text-[#8adcca] leading-relaxed">
                Let's get you set up in just a few steps. You'll configure your Azure AI Foundry
                project, choose which models to use, and optionally connect your database and tools.
              </p>
              <div className="terminal-panel p-4">
                <h3 className="terminal-label text-[#97ff8a] mb-2">prerequisites:</h3>
                <ul className="text-sm text-[#78adb8] space-y-1.5">
                  <li className="flex items-start gap-2">
                    <span className="mt-0.5 text-[#3dd8c5]">•</span>
                    <span>An <strong className="text-[#c9f6ef]">Azure AI Foundry project</strong> with at least one model deployed</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-0.5 text-[#3dd8c5]">•</span>
                    <span>An <strong className="text-[#c9f6ef]">Azure Cosmos DB</strong> account (for persistence)</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-0.5 text-[#3dd8c5]">•</span>
                    <span><strong className="text-[#c9f6ef]">Azure CLI</strong> logged in (<code className="text-xs bg-[#16120c] border border-[#3dd8c5]/18 px-1.5 py-0.5">az login</code>)</span>
                  </li>
                </ul>
              </div>
              <p className="text-sm text-[#486d78]">
                You can always change these settings later from the Settings panel.
              </p>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-4">
              <p className="text-[#78adb8] text-sm">
                Enter your Azure AI Foundry project endpoint. You can find this in the Azure AI Foundry portal
                under your project's overview page.
              </p>
              <div>
                <label className="terminal-label text-[#97ff8a] block mb-1.5">project endpoint</label>
                <input
                  type="text"
                  value={projectEndpoint}
                  onChange={(e) => setProjectEndpoint(e.target.value)}
                  placeholder="https://<resource>.services.ai.azure.com/api/projects/<project>"
                  className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-[#3dd8c5]"
                />
              </div>
              <div>
                <label className="terminal-label text-[#97ff8a] block mb-1.5">default model deployment</label>
                <select
                  value={modelDeployment}
                  onChange={(e) => setModelDeployment(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-gray-200 focus:outline-none focus:border-[#3dd8c5]"
                >
                  {!selectedModels.includes(modelDeployment) && modelDeployment && (
                    <option value={modelDeployment}>{modelDeployment}</option>
                  )}
                  {selectedModels.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                  {selectedModels.length === 0 && !modelDeployment && (
                    <option value="">Select a model</option>
                  )}
                </select>
                <p className="text-xs text-[#486d78] mt-1">Must match a deployment name in your Foundry project</p>
              </div>
              {projectEndpoint && (
                <button
                  onClick={handleTestFoundry}
                  disabled={foundryTest.status === "testing"}
                  className="terminal-control flex items-center gap-2 px-4 py-2 text-sm text-[#8adcca] transition-colors disabled:opacity-50 hover:bg-[#0f161b]"
                >
                  {foundryTest.status === "testing" ? (
                    <span className="w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                  )}
                  Test Connection
                </button>
              )}
              {foundryTest.status !== "idle" && foundryTest.status !== "testing" && (
                <div className={`text-sm px-3 py-2 rounded-lg ${foundryTest.status === "success" ? "bg-green-900/30 text-green-400 border border-green-800" : "bg-red-900/30 text-red-400 border border-red-800"}`}>
                  {foundryTest.message}
                </div>
              )}
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <p className="text-[#78adb8] text-sm">
                Select which models you want available in the model selector. These should match
                deployments in your Azure AI Foundry project.
              </p>

              {/* Load from Foundry */}
              <div className="flex items-center gap-2">
                <button
                  onClick={handleLoadDeployments}
                  disabled={deploymentsLoading || !projectEndpoint}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-amber-900/30 border border-amber-700 text-teal-300 hover:bg-amber-900/50 disabled:opacity-40 transition-colors"
                >
                  {deploymentsLoading ? <span className="w-3 h-3 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" /> : (
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                  )}
                  Load from Foundry
                </button>
                {deploymentsError && <span className="text-xs text-red-400">{deploymentsError}</span>}
                {foundryDeployments.length > 0 && !deploymentsError && (
                  <span className="text-xs text-green-400">{foundryDeployments.length} deployment{foundryDeployments.length !== 1 ? "s" : ""} found</span>
                )}
              </div>

              {/* Foundry deployments list */}
              {foundryDeployments.length > 0 && (
                <div className="terminal-panel divide-y divide-[#3dd8c5]/10">
                  {foundryDeployments.map((d) => (
                    <div key={d.name} className="flex items-center gap-3 px-3 py-2">
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium text-gray-200">{d.name}</div>
                        <div className="text-[10px] text-gray-500">{d.model_publisher} / {d.model_name} v{d.model_version}</div>
                      </div>
                      <button
                        onClick={() => { setModelDeployment(d.name); }}
                        className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
                          modelDeployment === d.name
                            ? "bg-amber-500 border-amber-500 text-[#071210]"
                            : "border-gray-600 text-gray-400 hover:border-amber-500 hover:text-teal-300"
                        }`}
                      >
                        {modelDeployment === d.name ? "Default" : "Set as default"}
                      </button>
                      <button
                        onClick={() => toggleModel(d.name)}
                        className={`w-4 h-4 rounded border flex items-center justify-center text-xs flex-shrink-0 ${
                          selectedModels.includes(d.name) ? "bg-amber-500 border-amber-500 text-[#071210]" : "border-gray-600"
                        }`}
                      >
                        {selectedModels.includes(d.name) && "✓"}
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Static model grid */}
              <div className="grid grid-cols-2 gap-2">
                {ALL_MODELS.map((model) => (
                  <button
                    key={model}
                    onClick={() => toggleModel(model)}
                    className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border text-sm text-left transition-colors ${
                      selectedModels.includes(model)
                        ? "bg-amber-900/30 border-amber-600 text-teal-200"
                        : "bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-600"
                    }`}
                  >
                    <div className={`w-4 h-4 rounded border flex items-center justify-center text-xs ${
                      selectedModels.includes(model) ? "bg-amber-500 border-amber-500 text-[#071210]" : "border-gray-600"
                    }`}>
                      {selectedModels.includes(model) && "✓"}
                    </div>
                    <span className="flex-1">{model}</span>
                    {selectedModels.includes(model) && (
                      <button
                        onClick={(e) => { e.stopPropagation(); setModelDeployment(model); }}
                        className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
                          modelDeployment === model
                            ? "bg-amber-500 border-amber-500 text-[#071210]"
                            : "border-gray-600 text-gray-400 hover:border-amber-500 hover:text-teal-300"
                        }`}
                      >
                        {modelDeployment === model ? "Default" : "Set as default"}
                      </button>
                    )}
                  </button>
                ))}
              </div>
              <div className="terminal-panel p-3">
                <p className="text-xs text-[#78adb8]">
                  <strong className="text-[#8adcca]">Tip:</strong> You can also type custom model names directly.
                  Add a custom deployment name:
                </p>
                <div className="flex gap-2 mt-2">
                  <input
                    type="text"
                    placeholder="custom-model-name"
                    className="flex-1 bg-gray-900 border border-gray-600 rounded-lg px-3 py-1.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-[#3dd8c5]"
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        const val = (e.target as HTMLInputElement).value.trim();
                        if (val && !selectedModels.includes(val)) {
                          setSelectedModels((prev) => [...prev, val]);
                          (e.target as HTMLInputElement).value = "";
                        }
                      }
                    }}
                  />
                  <span className="text-xs text-gray-500 self-center">Press Enter</span>
                </div>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4">
              <p className="text-[#78adb8] text-sm">
                Azure Cosmos DB is used to persist agents, conversations, and user settings.
                Enter your account details below.
              </p>
              <div>
                <label className="terminal-label text-[#97ff8a] block mb-1.5">cosmos db url</label>
                <input
                  type="text"
                  value={cosmosUrl}
                  onChange={(e) => setCosmosUrl(e.target.value)}
                  placeholder="https://<account>.documents.azure.com:443/"
                  className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-[#3dd8c5]"
                />
              </div>
              <div>
                <label className="terminal-label text-[#97ff8a] block mb-1.5">cosmos db key</label>
                <input
                  type="password"
                  value={cosmosKey}
                  onChange={(e) => setCosmosKey(e.target.value)}
                  placeholder="Your primary or secondary key"
                  className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-[#3dd8c5]"
                />
              </div>
              <div>
                <label className="terminal-label text-[#97ff8a] block mb-1.5">database name</label>
                <input
                  type="text"
                  value={cosmosDb}
                  onChange={(e) => setCosmosDb(e.target.value)}
                  placeholder="cronosaurus"
                  className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-[#3dd8c5]"
                />
              </div>
              {cosmosUrl && cosmosKey && (
                <button
                  onClick={handleTestCosmos}
                  disabled={cosmosTest.status === "testing"}
                  className="terminal-control flex items-center gap-2 px-4 py-2 text-sm text-[#8adcca] transition-colors disabled:opacity-50 hover:bg-[#0f161b]"
                >
                  {cosmosTest.status === "testing" ? (
                    <span className="w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                  )}
                  Test Connection
                </button>
              )}
              {cosmosTest.status !== "idle" && cosmosTest.status !== "testing" && (
                <div className={`text-sm px-3 py-2 rounded-lg ${cosmosTest.status === "success" ? "bg-green-900/30 text-green-400 border border-green-800" : "bg-red-900/30 text-red-400 border border-red-800"}`}>
                  {cosmosTest.message}
                </div>
              )}
            </div>
          )}

          {step === 4 && (
            <div className="space-y-4">
              <p className="text-[#78adb8] text-sm">
                Would you like to configure any of these optional tools? You can always set them up
                later from the Settings panel.
              </p>
              <div className="space-y-3">
                <button
                  onClick={() => setConfigureEmail(!configureEmail)}
                  className={`w-full flex items-center gap-4 p-4 rounded-lg border text-left transition-colors ${
                    configureEmail
                      ? "bg-amber-900/20 border-amber-700"
                      : "bg-gray-800 border-gray-700 hover:border-gray-600"
                  }`}
                >
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center text-lg ${
                    configureEmail ? "bg-amber-500 text-[#071210]" : "bg-gray-700"
                  }`}>
                    ✉️
                  </div>
                  <div className="flex-1">
                    <div className="text-sm font-medium text-gray-200">Email (SMTP/IMAP)</div>
                    <div className="text-xs text-gray-400">Let agents send and read emails on your behalf</div>
                  </div>
                  <div className={`w-5 h-5 rounded border flex items-center justify-center text-xs ${
                    configureEmail ? "bg-amber-500 border-amber-500 text-[#071210]" : "border-gray-600"
                  }`}>
                    {configureEmail && "✓"}
                  </div>
                </button>

                <button
                  onClick={() => setConfigureCosmos(!configureCosmos)}
                  className={`w-full flex items-center gap-4 p-4 rounded-lg border text-left transition-colors ${
                    configureCosmos
                      ? "bg-amber-900/20 border-amber-700"
                      : "bg-gray-800 border-gray-700 hover:border-gray-600"
                  }`}
                >
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center text-lg ${
                    configureCosmos ? "bg-amber-500 text-[#071210]" : "bg-gray-700"
                  }`}>
                    🗄️
                  </div>
                  <div className="flex-1">
                    <div className="text-sm font-medium text-gray-200">Azure Cosmos DB</div>
                    <div className="text-xs text-gray-400">Persist agents, conversations, and user settings across sessions</div>
                  </div>
                  <div className={`w-5 h-5 rounded border flex items-center justify-center text-xs ${
                    configureCosmos ? "bg-amber-500 border-amber-500 text-[#071210]" : "border-gray-600"
                  }`}>
                    {configureCosmos && "✓"}
                  </div>
                </button>
              </div>
              <p className="text-xs text-[#486d78]">
                These preferences are saved so you can return to set them up from the management panel.
              </p>
            </div>
          )}

          {step === 5 && (
            <div className="space-y-4">
              <div className="text-4xl mb-2 text-[#b0f0e8]">You're all set! 🚀</div>
              <p className="text-[#8adcca] leading-relaxed">
                Your Cronosaurus instance is configured and ready to go.
                Here's a summary of your setup:
              </p>
              <div className="terminal-panel divide-y divide-[#3dd8c5]/10">
                <div className="flex justify-between px-4 py-2.5">
                  <span className="text-sm text-[#78adb8]">AI Foundry</span>
                  <span className="text-sm text-[#c9f6ef] truncate ml-4 max-w-[300px]">{projectEndpoint || "Not set"}</span>
                </div>
                <div className="flex justify-between px-4 py-2.5">
                  <span className="text-sm text-[#78adb8]">Default Model</span>
                  <span className="text-sm text-[#c9f6ef]">{modelDeployment}</span>
                </div>
                <div className="flex justify-between px-4 py-2.5">
                  <span className="text-sm text-[#78adb8]">Models</span>
                  <span className="text-sm text-[#c9f6ef]">{selectedModels.length} selected</span>
                </div>
                <div className="flex justify-between px-4 py-2.5">
                  <span className="text-sm text-[#78adb8]">Cosmos DB</span>
                  <span className="text-sm text-[#c9f6ef]">{cosmosUrl ? "Configured" : "Not configured"}</span>
                </div>
                <div className="flex justify-between px-4 py-2.5">
                  <span className="text-sm text-[#78adb8]">Email</span>
                  <span className="text-sm text-[#c9f6ef]">{configureEmail ? "Will configure" : "Skipped"}</span>
                </div>
              </div>
              {error && (
                <div className="text-sm px-3 py-2 rounded-lg bg-red-900/30 text-red-400 border border-red-800">
                  {error}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer navigation */}
        <div className="px-6 py-4 border-t border-[#3dd8c5]/10 flex justify-between">
          <button
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0}
            className="terminal-control px-4 py-2 text-sm text-[#78adb8] hover:text-[#b0f0e8] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            back
          </button>
          <div className="flex gap-2">
            {step < 5 ? (
              <button
                onClick={() => setStep((s) => s + 1)}
                disabled={!canProceed()}
                className="brand-button-primary rounded-lg px-6 py-2 text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                Continue
              </button>
            ) : (
              <button
                onClick={handleFinish}
                disabled={saving}
                className="brand-button-primary rounded-lg px-6 py-2 text-sm font-semibold disabled:opacity-50 transition-all flex items-center gap-2"
              >
                {saving && <span className="w-4 h-4 border-2 border-[#071210] border-t-transparent rounded-full animate-spin" />}
                Get Started
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
