type ToggleAccent = "teal" | "green" | "purple" | "blue" | "amber";
type ToggleSize = "sm" | "md";

interface ToggleSwitchProps {
  checked: boolean;
  onToggle?: (next: boolean) => void;
  accent?: ToggleAccent;
  size?: ToggleSize;
  disabled?: boolean;
  title?: string;
  ariaLabel?: string;
  className?: string;
}

function joinClasses(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

export default function ToggleSwitch({
  checked,
  onToggle,
  accent = "teal",
  size = "md",
  disabled = false,
  title,
  ariaLabel,
  className,
}: ToggleSwitchProps) {
  const classes = joinClasses(
    "ui-toggle",
    `ui-toggle--${size}`,
    `ui-toggle--${accent}`,
    checked && "ui-toggle--checked",
    disabled && "ui-toggle--disabled",
    className,
  );

  const chrome = (
    <>
      <span className="ui-toggle__led" />
      <span className="ui-toggle__knob" />
    </>
  );

  if (!onToggle) {
    return <span aria-hidden="true" className={classes}>{chrome}</span>;
  }

  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel ?? title}
      title={title}
      disabled={disabled}
      className={classes}
      onClick={() => onToggle(!checked)}
    >
      {chrome}
    </button>
  );
}