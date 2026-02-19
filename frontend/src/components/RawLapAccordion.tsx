import { useState, useMemo } from "react";
import type { LapRecord } from "@/types/api";
import { formatLapTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Badge style for track state (dark theme) */
function getTrackStateBadgeClass(label: string | null | undefined): string {
  if (!label || label === "GREEN") return "";
  const l = String(label).toUpperCase();
  if (l === "RED") return "bg-red-500/25 text-red-200 border-red-500/40";
  if (l === "SC") return "bg-white/20 text-gray-200 border-white/30";
  if (l === "VSC") return "bg-blue-500/25 text-blue-200 border-blue-500/40";
  if (l.startsWith("YELLOW")) return "bg-amber-500/25 text-amber-200 border-amber-500/40";
  if (l === "GREEN") return "bg-emerald-500/15 text-emerald-300/90 border-emerald-500/30";
  return "bg-white/10 text-[var(--color-text-muted)] border-[var(--color-border)]";
}

/** Pit badge: separate from track state */
const PIT_BADGE_CLASS = "bg-purple-500/25 text-purple-200 border-purple-500/40";

export interface RawLapAccordionProps {
  laps: LapRecord[];
  className?: string;
}

export function RawLapAccordion({ laps, className }: RawLapAccordionProps) {
  const [open, setOpen] = useState(false);
  const [driver, setDriver] = useState("");
  const [compound, setCompound] = useState("");
  const [stint, setStint] = useState("");
  const [lapMin, setLapMin] = useState("");
  const [lapMax, setLapMax] = useState("");
  const [search, setSearch] = useState("");

  const drivers = useMemo(
    () => [...new Set(laps.map((l) => l.driver).filter(Boolean))].sort() as string[],
    [laps]
  );
  const compounds = useMemo(
    () => [...new Set(laps.map((l) => l.compound).filter(Boolean))].sort() as string[],
    [laps]
  );
  const stints = useMemo(
    () =>
      [...new Set(laps.map((l) => l.stint).filter((v) => v != null))].sort(
        (a, b) => Number(a) - Number(b)
      ) as (number | string)[],
    [laps]
  );

  const filtered = useMemo(() => {
    const searchLower = search.toLowerCase();
    return laps.filter((l) => {
      if (driver && l.driver !== driver) return false;
      if (compound && String(l.compound) !== compound) return false;
      if (stint !== "" && l.stint != null && Number(l.stint) !== Number(stint))
        return false;
      const lapNum = l.lap ?? l.lap_number;
      if (lapMin && lapNum != null && lapNum < Number(lapMin)) return false;
      if (lapMax && lapNum != null && lapNum > Number(lapMax)) return false;
      if (
        search &&
        !(String(l.driver ?? "") + " " + String(l.team ?? ""))
          .toLowerCase()
          .includes(searchLower)
      )
        return false;
      return true;
    });
  }, [laps, driver, compound, stint, lapMin, lapMax, search]);

  return (
    <div className={cn("mt-6", className)}>
      <button
        type="button"
        className="flex w-full items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-5 py-3.5 font-semibold text-[var(--color-text-default)] hover:bg-[var(--color-bg-card)]"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        Raw Lap Data
        <span
          className={cn(
            "text-[var(--color-secondary)] transition-transform",
            !open && "-rotate-90"
          )}
        >
          ▼
        </span>
      </button>
      {open && (
        <div className="rounded-b-lg border border-t-0 border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
          <div className="mb-4 flex flex-wrap gap-3 items-end">
            <label className="flex flex-col gap-1 text-sm">
              Driver
              <select
                value={driver}
                onChange={(e) => setDriver(e.target.value)}
                className="rounded border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-2 py-1.5 text-sm text-[var(--color-text-default)] w-[140px]"
              >
                <option value="">All</option>
                {drivers.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Compound
              <select
                value={compound}
                onChange={(e) => setCompound(e.target.value)}
                className="rounded border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-2 py-1.5 text-sm text-[var(--color-text-default)] w-[120px]"
              >
                <option value="">All</option>
                {compounds.map((c) => (
                  <option key={c} value={String(c)}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Stint
              <select
                value={stint}
                onChange={(e) => setStint(e.target.value)}
                className="rounded border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-2 py-1.5 text-sm text-[var(--color-text-default)] w-[80px]"
              >
                <option value="">All</option>
                {stints.map((s) => (
                  <option key={s} value={String(s)}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Lap min
              <input
                type="number"
                min={1}
                placeholder="Min"
                value={lapMin}
                onChange={(e) => setLapMin(e.target.value)}
                className="w-20 rounded border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-2 py-1.5 text-sm text-[var(--color-text-default)]"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Lap max
              <input
                type="number"
                placeholder="Max"
                value={lapMax}
                onChange={(e) => setLapMax(e.target.value)}
                className="w-20 rounded border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-2 py-1.5 text-sm text-[var(--color-text-default)]"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Search
              <input
                type="text"
                placeholder="Driver, team..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-36 rounded border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-2 py-1.5 text-sm text-[var(--color-text-default)]"
              />
            </label>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/5 backdrop-blur">
            <div className="max-h-[520px] overflow-auto">
              <table className="w-full min-w-[800px] table-fixed text-sm border-collapse">
                <colgroup>
                  <col className="w-[90px]" />
                  <col className="w-[100px]" />
                  <col className="w-[120px]" />
                  <col className="w-[80px]" />
                  <col className="w-[72px]" />
                  <col className="w-[56px]" />
                  <col className="w-[88px]" />
                  <col className="w-[56px]" />
                </colgroup>
                <thead className="sticky top-0 z-20 bg-black/60 backdrop-blur">
                  <tr className="text-xs font-semibold uppercase text-white/80">
                    <th className="sticky left-0 z-30 bg-black/60 px-3 py-2 text-left whitespace-nowrap border-b border-white/10 border-r border-white/10">
                      Driver
                    </th>
                    <th className="sticky left-[90px] z-30 bg-black/60 px-3 py-2 text-left whitespace-nowrap border-b border-white/10 border-r border-white/10">
                      Team
                    </th>
                    <th className="px-3 py-2 text-right whitespace-nowrap border-b border-white/10 font-mono">
                      Lap
                    </th>
                    <th className="px-3 py-2 text-right whitespace-nowrap border-b border-white/10 font-mono">
                      Lap time
                    </th>
                    <th className="px-3 py-2 text-left whitespace-nowrap border-b border-white/10">
                      Compound
                    </th>
                    <th className="px-3 py-2 text-right whitespace-nowrap border-b border-white/10 font-mono">
                      Stint
                    </th>
                    <th className="px-3 py-2 text-left whitespace-nowrap border-b border-white/10">
                      Track state
                    </th>
                    <th className="px-3 py-2 text-left whitespace-nowrap border-b border-white/10">
                      Pit
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((lap, i) => {
                    const lapNum = lap.lap ?? lap.lap_number;
                    const lapNumDisplay =
lapNum ?? "–";
                    const isPit = lap.pit_lap || lap.is_pit_lap;
                    const stateLabel = lap.state_label ?? lap.track_state ?? null;
                    const trackBadgeClass = getTrackStateBadgeClass(stateLabel);
                    const yellowSectors = lap.yellow_sectors ?? [];
                    const yellowLabel =
                      yellowSectors.length > 0
                        ? `Y ${yellowSectors.map((s) => `S${s}`).join("+")}`
                        : stateLabel;
                    return (
                      <tr
                        key={i}
                        className="border-t border-white/5 hover:bg-white/5"
                      >
                        <td className="sticky left-0 z-10 bg-black/40 px-3 py-2 whitespace-nowrap text-[var(--color-text-muted)] border-r border-white/5">
                          {lap.driver ?? "–"}
                        </td>
                        <td className="sticky left-[90px] z-10 bg-black/40 px-3 py-2 whitespace-nowrap text-[var(--color-text-muted)] border-r border-white/5">
                          {lap.team ?? "–"}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap text-right font-mono tabular-nums text-white/80">
                          {lapNumDisplay}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap text-right font-mono tabular-nums text-white/80">
                          {formatLapTime(
                            lap.lap_time_s != null ? Number(lap.lap_time_s) : undefined
                          )}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap text-[var(--color-text-muted)]">
                          {lap.compound ?? "–"}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap text-right font-mono tabular-nums text-white/80">
                          {lap.stint ?? "–"}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          {stateLabel && stateLabel !== "GREEN" ? (
                            <span
                              className={cn(
                                "inline-flex rounded border px-1.5 py-0.5 text-xs font-medium",
                                trackBadgeClass ||
                                  "bg-emerald-500/15 text-emerald-300/90 border-emerald-500/30"
                              )}
                            >
                              {yellowLabel}
                            </span>
                          ) : (
                            <span className="text-white/50 text-xs">GREEN</span>
                          )}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          {isPit ? (
                            <span
                              className={cn(
                                "inline-flex rounded border px-1.5 py-0.5 text-xs font-medium",
                                PIT_BADGE_CLASS
                              )}
                            >
                              PIT
                            </span>
                          ) : (
                            <span className="text-white/50">–</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
