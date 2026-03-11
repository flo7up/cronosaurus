interface ModelSelectorProps {
  models: string[];
  selectedModel: string;
  onChange: (model: string) => void;
  disabled?: boolean;
}

export default function ModelSelector({
  models,
  selectedModel,
  onChange,
  disabled = false,
}: ModelSelectorProps) {
  return (
    <div className="relative">
      <select
        value={selectedModel}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="terminal-control appearance-none text-sm
          px-3 py-1.5 pr-8 focus:outline-none
          disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer
          hover:border-[#8f7130] transition-colors uppercase tracking-[0.08em]"
      >
        {models.map((model) => (
          <option key={model} value={model}>
            {model}
          </option>
        ))}
      </select>
      <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
        <svg
          className="w-4 h-4 text-[#78adb8]"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 9l-7 7-7-7"
          />
        </svg>
      </div>
    </div>
  );
}
