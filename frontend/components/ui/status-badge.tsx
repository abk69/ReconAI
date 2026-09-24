import type { RiskBand, SignalTone } from "@/types/domain";

const toneClass: Record<SignalTone, string> = {
  success: "bg-success-soft text-success border-success/25",
  warning: "bg-warning-soft text-warning border-warning/25",
  danger: "bg-danger-soft text-danger border-danger/25",
  info: "bg-info-soft text-info border-info/25",
  neutral: "bg-neutral-soft text-neutral border-line",
};

const bandTone: Record<RiskBand, SignalTone> = {
  LOW: "success",
  MEDIUM: "warning",
  HIGH: "danger",
  CRITICAL: "danger",
};

type StatusBadgeProps = {
  label: string;
  tone?: SignalTone;
};

export function StatusBadge({ label, tone = "neutral" }: StatusBadgeProps) {
  const critical = label === "CRITICAL";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium tracking-wide ${toneClass[tone]} ${
        critical ? "border-danger/50" : ""
      }`}
    >
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
      {label}
    </span>
  );
}

export function RiskBandBadge({ band }: { band: RiskBand }) {
  return <StatusBadge label={band} tone={bandTone[band]} />;
}
