import * as React from "react";
import { cn } from "@/lib/utils";

export interface ColoredCheckboxProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label: string;
  color: string;
  id?: string;
  className?: string;
  disabled?: boolean;
}

/**
 * Colored checkbox in OriginUI style: driver-colored box, clear checked state,
 * dark-theme friendly. Label is clickable; keyboard focus visible.
 */
export function ColoredCheckbox({
  checked,
  onCheckedChange,
  label,
  color,
  id: idProp,
  className,
  disabled = false,
}: ColoredCheckboxProps) {
  const id = React.useId();
  const inputId = idProp ?? id;

  return (
    <label
      htmlFor={inputId}
      className={cn(
        "inline-flex cursor-pointer items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)]/60 px-2.5 py-1.5 transition-colors hover:border-white/15 hover:bg-[var(--color-bg-card)]/80 focus-within:ring-2 focus-within:ring-[var(--accent1)]/40 focus-within:ring-offset-2 focus-within:ring-offset-[var(--bg)]",
        disabled && "cursor-not-allowed opacity-60",
        className
      )}
    >
      <input
        id={inputId}
        type="checkbox"
        checked={checked}
        onChange={(e) => onCheckedChange(e.target.checked)}
        disabled={disabled}
        className="sr-only"
        aria-label={label}
      />
      <span
        className={cn(
          "flex h-5 w-5 shrink-0 items-center justify-center rounded border-2 transition-colors pointer-events-none",
          checked ? "border-transparent" : "border-current"
        )}
        style={{
          backgroundColor: checked ? color : "transparent",
          borderColor: checked ? color : "var(--color-border)",
          color: checked ? (isLight(color) ? "#0f172a" : "#f1f5f9") : "var(--color-text-muted)",
        }}
        aria-hidden
      >
        {checked && (
          <svg
            className="h-3 w-3 shrink-0"
            viewBox="0 0 12 12"
            fill="none"
            stroke="currentColor"
            strokeWidth={2.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M2 6l3 3 5-6" />
          </svg>
        )}
      </span>
      <span className="text-sm font-medium text-[var(--color-text-default)] select-none pointer-events-none">
        {label}
      </span>
    </label>
  );
}

/** Heuristic: treat color as "light" for checkmark contrast */
function isLight(hex: string): boolean {
  const m = hex.match(/^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i);
  if (!m) return false;
  const r = parseInt(m[1], 16);
  const g = parseInt(m[2], 16);
  const b = parseInt(m[3], 16);
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.6;
}
