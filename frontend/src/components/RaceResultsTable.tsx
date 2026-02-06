import type { RaceResultRow, RaceInfo } from "@/types/api";
import { cn } from "@/lib/utils";

export interface RaceResultsTableProps {
  raceInfo: RaceInfo;
  results: RaceResultRow[];
  /** "finish" shows Fastest Lap column; "performance" shows Performance column */
  view: "finish" | "performance";
  className?: string;
}

export function RaceResultsTable({
  raceInfo,
  results,
  view,
  className,
}: RaceResultsTableProps) {
  return (
    <div className={cn("space-y-6", className)}>
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--panel)] p-6 text-center shadow-[var(--shadow)] backdrop-blur-[14px]">
        <h2 className="text-[var(--color-text-default)] text-xl font-semibold">
          {raceInfo.raceName}
        </h2>
        <p className="mt-1 text-sm text-[var(--color-text-muted)]">
          {raceInfo.season} Season – Round {raceInfo.round}
        </p>
      </div>
      <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--panel)] shadow-[var(--shadow)] backdrop-blur-[14px]">
        <table className="w-full border-collapse bg-transparent">
          <thead className="bg-[var(--panel2)] text-[var(--color-text-default)]">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider">
                Pos
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider">
                Driver
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider">
                Constructor
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider">
                Grid
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider">
                Status
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider">
                Time
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider">
                Points
              </th>
              {view === "finish" ? (
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider">
                  Fastest Lap
                </th>
              ) : (
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider">
                  Performance
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {results.map((row) => {
              const statusClass =
                row.status === "DNF"
                  ? "retired"
                  : row.status === "Finished"
                    ? "finished"
                    : "finished";
              const statusLabel = row.status === "DNF" ? "DNF" : row.status;
              const dnfTitle =
                row.status === "DNF" && (row.dnf_reason || row.dnf_lap != null)
                  ? [
                      row.dnf_reason && `Reason: ${row.dnf_reason}`,
                      row.dnf_lap != null && `Lap: ${row.dnf_lap}`,
                    ]
                      .filter(Boolean)
                      .join(" | ")
                  : undefined;
              return (
                <tr
                  key={`${row.driver}-${row.Finish}`}
                  className={cn(
                    "border-t border-[var(--border)] hover:bg-white/[0.04]",
                    row.has_fastest_lap && "bg-[var(--color-quaternary)]/10 font-semibold"
                  )}
                >
                  <td className="px-4 py-3 text-center font-bold text-[var(--color-text-default)]">
                    {row.Finish}
                  </td>
                  <td className="px-4 py-3 text-[var(--color-text-default)]">
                    {row.driver}
                  </td>
                  <td className="px-4 py-3 text-[var(--color-text-muted)]">
                    {row.constructor}
                  </td>
                  <td className="px-4 py-3 text-[var(--color-text-muted)]">
                    {row.grid}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={cn(
                        "inline-block rounded px-2 py-0.5 text-xs font-semibold",
                        statusClass === "retired" &&
                          "bg-[var(--color-tertiary)]/20 text-[var(--color-tertiary)]",
                        statusClass === "finished" &&
                          "bg-[var(--color-secondary)]/20 text-[var(--color-secondary)]"
                      )}
                      title={dnfTitle}
                    >
                      {statusLabel}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-[var(--color-text-muted)]">
                    {row.time}
                  </td>
                  <td className="px-4 py-3 text-[var(--color-text-muted)]">
                    {row.points}
                  </td>
                  {view === "finish" ? (
                    <td className="px-4 py-3 text-[var(--color-text-muted)]">
                      {row.fastest_lap ?? "–"}
                    </td>
                  ) : (
                    <td className="px-4 py-3 font-semibold text-[var(--color-quinary)]">
                      {row.Performance != null
                        ? Number(row.Performance).toFixed(3)
                        : "–"}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
