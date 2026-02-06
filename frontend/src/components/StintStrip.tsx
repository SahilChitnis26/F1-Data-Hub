import type { StintRange } from "@/types/api";
import { COMPOUND_COLORS } from "@/components/charts/PaceDeltaChart";
import { cn } from "@/lib/utils";

export interface StintStripProps {
  /** Stint ranges grouped by driver (or flat list; we group by driver) */
  stintRanges: StintRange[];
  /** Drivers to show (selected drivers from chart) */
  selectedDrivers: string[];
  /** Max lap number for width calculation */
  maxLap: number;
  className?: string;
}

/** Minimum segment width (as % of bar) to show inline label; smaller segments get tooltip only */
const MIN_WIDTH_PCT_FOR_LABEL = 10;

/** Fixed row height (px) for consistent layout */
const ROW_HEIGHT = 28;

/** Max height of scrollable strip area when many drivers */
const MAX_STRIP_HEIGHT = 320;

function compoundInitial(compound: string | undefined): string {
  if (!compound) return "?";
  const c = compound.toUpperCase();
  if (c === "INTERMEDIATE") return "I";
  if (c === "SOFT" || c === "MEDIUM" || c === "HARD" || c === "WET") return c.charAt(0);
  return c.charAt(0);
}


export function StintStrip({
  stintRanges,
  selectedDrivers,
  maxLap,
  className,
}: StintStripProps) {
  const byDriver: Record<string, StintRange[]> = {};
  stintRanges.forEach((r) => {
    if (!byDriver[r.driver]) byDriver[r.driver] = [];
    byDriver[r.driver].push(r);
  });

  if (selectedDrivers.length === 0) return null;

  const totalRows = selectedDrivers.filter((d) => (byDriver[d] ?? []).length > 0).length;
  const scrollable = totalRows > 10;

  return (
    <div className={cn("flex flex-col", className)}>
      <div
        className={cn(
          "flex flex-col gap-1",
          scrollable && "overflow-y-auto overscroll-contain"
        )}
        style={scrollable ? { maxHeight: MAX_STRIP_HEIGHT } : undefined}
      >
        {selectedDrivers.map((driver) => {
          const ranges = (byDriver[driver] ?? []).sort(
            (a, b) => (a.stint ?? 0) - (b.stint ?? 0)
          );
          if (ranges.length === 0) return null;

          return (
            <div
              key={driver}
              className="flex items-center gap-2 shrink-0"
              style={{ minHeight: ROW_HEIGHT }}
            >
              <div className="w-14 shrink-0 text-right text-xs font-medium text-[var(--color-text-default)] tabular-nums">
                {driver}
              </div>
              <div className="flex flex-1 min-w-0 h-6 rounded overflow-hidden border border-[var(--color-border)]/50 bg-[var(--color-bg-elevated)]">
                {ranges.map((r, i) => {
                  const compound = (r.compound ?? "UNKNOWN").toUpperCase();
                  const color =
                    COMPOUND_COLORS[compound] ?? COMPOUND_COLORS.UNKNOWN;
                  const widthPct =
                    maxLap > 0 ? (r.length_laps / maxLap) * 100 : 0;
                  const showLabel =
                    widthPct >= MIN_WIDTH_PCT_FOR_LABEL && r.length_laps >= 1;
                  const label = showLabel
                    ? `${r.start_lap}–${r.end_lap} ${compoundInitial(r.compound)}`
                    : "";
                  const tooltip = `${r.compound ?? "Compound"}: Laps ${r.start_lap}–${r.end_lap} (${r.length_laps} laps)`;

                  return (
                    <div
                      key={`${r.stint}-${r.start_lap}`}
                      className={cn(
                        "flex items-center justify-center shrink-0 border-r border-black/20 last:border-r-0 transition-colors",
                        showLabel
                          ? "px-1 text-[10px] font-medium overflow-hidden text-black"
                          : "px-0"
                      )}
                      style={{
                        width: `${widthPct}%`,
                        background: color,
                        textShadow: "0 0 1px rgba(255,255,255,0.5)",
                      }}
                      title={tooltip}
                    >
                      {showLabel ? (
                        <span className="truncate block text-center">
                          {label}
                        </span>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
      {/* Lap scale */}
      {maxLap > 0 && (
        <div className="flex items-center gap-2 mt-1.5 pl-[3.5rem] min-w-0">
          <div className="flex flex-1 min-w-0 text-[10px] text-black justify-between tabular-nums">
            <span>1</span>
            {maxLap > 10 && <span>{Math.round(maxLap * 0.25)}</span>}
            {maxLap > 20 && <span>{Math.round(maxLap * 0.5)}</span>}
            {maxLap > 10 && <span>{Math.round(maxLap * 0.75)}</span>}
            <span>{maxLap}</span>
          </div>
        </div>
      )}
    </div>
  );
}
