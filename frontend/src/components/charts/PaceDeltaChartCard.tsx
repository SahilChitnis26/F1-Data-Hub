import { useState, useMemo } from "react";
import { PaceDeltaChart, COMPOUND_COLORS } from "@/components/charts/PaceDeltaChart";
import { StintStrip } from "@/components/StintStrip";
import type { LapWithDelta, StintRange } from "@/types/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface PaceDeltaChartCardProps {
  lapsWithDelta: LapWithDelta[];
  stintRanges: StintRange[];
  title?: string;
  height?: number;
  /** When provided, selection is controlled by parent (e.g. DriverFilterPanel on page). */
  selectedDrivers?: string[];
  onSelectedDriversChange?: (next: Set<string>) => void;
}

export function PaceDeltaChartCard({
  lapsWithDelta,
  stintRanges,
  title = "Pace delta vs race-median (clean laps)",
  height = 360,
  selectedDrivers: controlledSelected,
  onSelectedDriversChange,
}: PaceDeltaChartCardProps) {
  const drivers = useMemo(
    () =>
      [...new Set(lapsWithDelta.map((l) => l.driver).filter(Boolean))] as string[],
    [lapsWithDelta]
  );
  const [internalSelected, setInternalSelected] = useState<Set<string>>(
    () => new Set(drivers)
  );
  const [colorByCompound, setColorByCompound] = useState(true);

  const isControlled = controlledSelected !== undefined && onSelectedDriversChange !== undefined;
  const selectedSet = isControlled ? new Set(controlledSelected) : internalSelected;
  const selectedList = useMemo(
    () => drivers.filter((d) => selectedSet.has(d)),
    [drivers, selectedSet]
  );
  const maxLap = useMemo(
    () =>
      Math.max(
        ...lapsWithDelta.map((l) => l.lap_number ?? l.lap ?? 0),
        1
      ),
    [lapsWithDelta]
  );

  const usedCompounds = useMemo(
    () =>
      [...new Set(lapsWithDelta.map((l) => l.compound).filter(Boolean))] as string[],
    [lapsWithDelta]
  );

  const toggleDriver = (driver: string) => {
    const next = new Set(selectedSet);
    if (next.has(driver)) next.delete(driver);
    else next.add(driver);
    if (isControlled) onSelectedDriversChange?.(next);
    else setInternalSelected(next);
  };

  return (
    <Card className="border-[var(--color-border)] bg-[var(--color-bg-card)]">
      <CardHeader>
        <CardTitle className="text-[var(--color-text-default)]">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {!isControlled && (
        <div className="flex flex-wrap gap-4 items-start">
          <div className="flex flex-wrap gap-x-4 gap-y-2 max-h-18 overflow-y-auto min-w-[200px]">
            {drivers.map((d) => (
              <label
                key={d}
                className="flex items-center gap-2 cursor-pointer text-sm text-[var(--color-text-muted)]"
              >
                <input
                  type="checkbox"
                  checked={selectedSet.has(d)}
                  onChange={() => toggleDriver(d)}
                  className="rounded border-[var(--color-border)]"
                />
                {d}
              </label>
            ))}
          </div>
          <div className="flex flex-col gap-1.5 text-sm">
            <label className="flex items-center gap-2 cursor-pointer text-[var(--color-text-muted)]">
              <input
                type="checkbox"
                checked={colorByCompound}
                onChange={(e) => setColorByCompound(e.target.checked)}
                className="rounded border-[var(--color-border)]"
              />
              Color line by compound
            </label>
          </div>
        </div>
        )}
        {usedCompounds.length > 0 && (
          <div className="flex flex-wrap gap-4 text-sm">
            {usedCompounds.map((c) => {
              const color =
                COMPOUND_COLORS[c.toUpperCase()] ?? COMPOUND_COLORS.UNKNOWN;
              return (
                <div
                  key={c}
                  className="flex items-center gap-2 text-[var(--color-text-muted)]"
                >
                  <span
                    className="h-1 w-6 rounded-full"
                    style={{ background: color }}
                  />
                  {c}
                </div>
              );
            })}
          </div>
        )}
        <StintStrip
          stintRanges={stintRanges}
          selectedDrivers={selectedList}
          maxLap={maxLap}
        />
        <PaceDeltaChart
          lapsWithDelta={lapsWithDelta}
          colorByCompound={colorByCompound}
          selectedDrivers={isControlled ? controlledSelected : (selectedList.length > 0 ? selectedList : undefined)}
          height={height}
          embedded
        />
      </CardContent>
    </Card>
  );
}
