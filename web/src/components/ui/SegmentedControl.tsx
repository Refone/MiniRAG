interface SegmentedControlProps<T extends string> {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  disabled?: boolean;
  /** 无障碍分组标签 */
  ariaLabel?: string;
}

/** 分段开关（thumb 滑动）：选项顺序即展示顺序 */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  disabled = false,
  ariaLabel,
}: SegmentedControlProps<T>) {
  const index = Math.max(options.findIndex((o) => o.value === value), 0);
  return (
    <div
      className={`segmented${disabled ? " disabled" : ""}`}
      role="group"
      aria-label={ariaLabel}
    >
      <div
        className="seg-thumb"
        style={{ transform: `translateX(${index * 100}%)` }}
      />
      {options.map((o) => (
        <button
          key={o.value}
          className={`seg-btn${value === o.value ? " active" : ""}`}
          type="button"
          disabled={disabled}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
