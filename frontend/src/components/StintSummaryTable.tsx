import { useState, useMemo } from "react";
import type { StintSummaryRow } from "@/types/api";
import { formatLapTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const SORT_KEYS = [
  "driver",
  "team",
  "stint",
  "compound",
  "laps_in_stint",
  "avg_lap_time",
  "fastest_lap_time",
  "std_dev",
  "degradation_slope_sec_per_lap",
  "avg_pace_delta",
] as const;

const NUM_KEYS = new Set([
  "stint",
  "laps_in_stint",
  "avg_lap_time",
  "fastest_lap_time",
  "std_dev",
  "degradation_slope_sec_per_lap",
  "avg_pace_delta",
]);

type SortKey = (typeof SORT_KEYS)[number];

const COLUMNS: {
  key: SortKey;
  shortLabel: string;
  tooltip: string;
  numeric: boolean;
  minWidth: string;
  sticky?: boolean;
}[] = [
  { key: "driver", shortLabel: "Driver", tooltip: "Driver name", numeric: false, minWidth: "min-w-[90px]", sticky: true },
  { key: "team", shortLabel: "Team", tooltip: "Constructor / team", numeric: false, minWidth: "min-w-[100px]", sticky: true },
  { key: "stint", shortLabel: "Stint", tooltip: "Stint number", numeric: true, minWidth: "min-w-[56px]" },
  { key: "compound", shortLabel: "Compound", tooltip: "Tyre compound", numeric: false, minWidth: "min-w-[72px]" },
  { key: "laps_in_stint", shortLabel: "Laps", tooltip: "Laps in stint", numeric: true, minWidth: "min-w-[52px]" },
  { key: "avg_lap_time", shortLabel: "Avg lap", tooltip: "Average lap time", numeric: true, minWidth: "min-w-[80px]" },
  { key: "fastest_lap_time", shortLabel: "Fastest", tooltip: "Fastest lap time in stint", numeric: true, minWidth: "min-w-[80px]" },
  { key: "std_dev", shortLabel: "Std dev", tooltip: "Standard deviation of lap times", numeric: true, minWidth: "min-w-[72px]" },
  { key: "degradation_slope_sec_per_lap", shortLabel: "Deg slope", tooltip: "Degradation slope (sec per lap)", numeric: true, minWidth: "min-w-[80px]" },
  { key: "avg_pace_delta", shortLabel: "Avg pace Δ", tooltip: "Average pace delta vs race median", numeric: true, minWidth: "min-w-[80px]" },
];

export interface StintSummaryTableProps {
  data: StintSummaryRow[];
  className?: string;
}

export function StintSummaryTable({ data, className }: StintSummaryTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("driver");

  const sorted = useMemo(() => {
    const key = sortKey;
    const isNum = NUM_KEYS.has(key);
    return [...data].sort((a, b) => {
      let va = a[key as keyof StintSummaryRow];
      let vb = b[key as keyof StintSummaryRow];
      if (va == null) va = isNum ? (Infinity as unknown as string) : "";
      if (vb == null) vb = isNum ? (Infinity as unknown as string) : "";
      if (isNum)
        return (Number(va) || 0) - (Number(vb) || 0);
      return String(va).localeCompare(String(vb));
    });
  }, [data, sortKey]);

  return (
    <div className={cn("space-y-3", className)}>
      <h3 className="text-[var(--color-text-default)] font-semibold">
        Stint Summary
      </h3>
      <div className="rounded-xl border border-white/10 bg-white/5 backdrop-blur">
        <div className="max-h-[520px] overflow-auto">
          <table className="w-full min-w-[1100px] table-fixed text-sm border-collapse">
            <colgroup>
              <col className="w-[90px]" />
              <col className="w-[100px]" />
              <col className="w-[56px]" />
              <col className="w-[72px]" />
              <col className="w-[52px]" />
              <col className="w-[80px]" />
              <col className="w-[80px]" />
              <col className="w-[72px]" />
              <col className="w-[80px]" />
              <col className="w-[80px]" />
            </colgroup>
            <thead className="sticky top-0 z-20 bg-black/60 backdrop-blur">
              <tr className="text-xs font-semibold tracking-wide text-white/80">
                {COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    title={col.tooltip}
                    className={cn(
                      "cursor-pointer select-none px-3 py-3.5 whitespace-nowrap hover:text-[var(--color-secondary)] border-b border-white/10 bg-black/60",
                      col.numeric ? "text-right" : "text-left",
                      col.sticky && col.key === "driver" && "sticky left-0 z-30 border-r border-white/10 pl-4",
                      col.sticky && col.key === "team" && "sticky left-[90px] z-30 border-r border-white/10"
                    )}
                    onClick={() => setSortKey(col.key)}
                  >
                    {col.shortLabel}
                    <span className="ml-0.5 opacity-50">⇅</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((row, i) => (
                <tr
                  key={i}
                  className={cn(
                    "border-t border-white/5 hover:bg-white/5",
                    i % 2 === 1 && "bg-white/[0.02]"
                  )}
                >
                  <td
                    className="sticky left-0 z-10 bg-black/40 px-3 py-3 whitespace-nowrap text-[var(--color-text-muted)] border-r border-white/5 pl-4"
                  >
                    {String(row.driver ?? "–")}
                  </td>
                  <td
                    className="sticky left-[90px] z-10 bg-black/40 px-3 py-3 whitespace-nowrap text-[var(--color-text-muted)] border-r border-white/5"
                  >
                    {String(row.team ?? "–")}
                  </td>
                  <td className="px-3 py-3 whitespace-nowrap text-right font-mono tabular-nums text-white/80">
                    {row.stint ?? "–"}
                  </td>
                  <td className="px-3 py-3 whitespace-nowrap text-[var(--color-text-muted)]">
                    {String(row.compound ?? "–")}
                  </td>
                  <td className="px-3 py-3 whitespace-nowrap text-right font-mono tabular-nums text-white/80">
                    {row.laps_in_stint ?? "–"}
                  </td>
                  <td className="px-3 py-3 whitespace-nowrap text-right font-mono tabular-nums text-white/80">
                    {formatLapTime(row.avg_lap_time ?? undefined)}
                  </td>
                  <td className="px-3 py-3 whitespace-nowrap text-right font-mono tabular-nums text-white/80">
                    {formatLapTime(row.fastest_lap_time ?? undefined)}
                  </td>
                  <td className="px-3 py-3 whitespace-nowrap text-right font-mono tabular-nums text-white/80">
                    {row.std_dev != null ? Number(row.std_dev).toFixed(3) : "–"}
                  </td>
                  <td className="px-3 py-3 whitespace-nowrap text-right font-mono tabular-nums text-white/80">
                    {row.degradation_slope_sec_per_lap != null
                      ? Number(row.degradation_slope_sec_per_lap).toFixed(4)
                      : "–"}
                  </td>
                  <td className="px-3 py-3 whitespace-nowrap text-right font-mono tabular-nums text-white/80">
                    {row.avg_pace_delta != null
                      ? Number(row.avg_pace_delta).toFixed(3)
                      : "–"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
