import { useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import type { Payload } from "recharts/types/component/DefaultTooltipContent";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/** F1 compound colors (Pirelli-style) */
export const COMPOUND_COLORS: Record<string, string> = {
  SOFT: "#ff3333",
  MEDIUM: "#ffcc00",
  HARD: "#ffffff",
  INTERMEDIATE: "#43b02a",
  WET: "#0066ff",
  UNKNOWN: "#888888",
};

/** Driver line colors (up to 20 drivers) */
export const DRIVER_COLORS = [
  "#73cfa8",
  "#73b1ff",
  "#fde179",
  "#fb9289",
  "#c084fc",
  "#94a3b8",
  "#f472b6",
  "#34d399",
  "#fbbf24",
  "#a78bfa",
  "#22d3ee",
  "#a3e635",
  "#f97316",
  "#e879f9",
  "#38bdf8",
  "#4ade80",
  "#facc15",
  "#fb7185",
  "#818cf8",
  "#2dd4bf",
];

/** Single lap point for the chart */
export type LapPoint = {
  lap: number;
  delta: number | null;
  isPitLap?: boolean;
  compound?: string | null;
  tyreAge?: number | null;
  trackStatus?: string | null;
  driver: string;
};

/** One series per driver */
export type DriverSeries = {
  driver: string;
  points: LapPoint[];
};

/** API lap row (computed.laps_with_delta); may include extra fields from backend */
export interface LapWithDelta {
  driver: string;
  lap_number?: number;
  lap?: number;
  pace_delta?: number | null;
  compound?: string | null;
  stint?: number | null;
  is_pit_lap?: boolean | null;
  pit_lap?: boolean | null;
  is_pit_out_lap?: boolean | null;
  is_in_lap?: boolean | null;
  lap_index_in_stint?: number | null;
  is_track_green?: boolean | null;
  /** Display label: GREEN | SC | VSC | RED | YELLOW S1 | YELLOW S1+S2 etc. */
  state_label?: string | null;
  track_state?: string | null;
  yellow_sectors?: number[] | null;
}

export interface PaceDeltaChartProps {
  lapsWithDelta: LapWithDelta[];
  title?: string;
  colorByCompound?: boolean;
  selectedDrivers?: string[];
  height?: number;
  embedded?: boolean;
}

const MAX_DRIVERS = 20;

/** Build lookup key for (lap, driver) */
function pointKey(lap: number, driver: string): string {
  return `${lap}-${driver}`;
}

/**
 * Transform API laps_with_delta into DriverSeries[] (all drivers, up to MAX_DRIVERS)
 * and recharts data + point lookup. Derives isPitLap from is_pit_lap / pit_lap / is_pit_out_lap | is_in_lap.
 */
function transformToSeriesShowAll(laps: LapWithDelta[]): {
  series: DriverSeries[];
  rechartsData: { lap: number; [driver: string]: number | undefined }[];
  pointLookup: Map<string, LapPoint>;
  driverColors: Map<string, string>;
} {
  const byDriver: Record<string, LapPoint[]> = {};
  const driverColors = new Map<string, string>();
  const drivers = [...new Set(laps.map((l) => l.driver).filter(Boolean))].slice(0, MAX_DRIVERS);

  drivers.forEach((driver, i) => {
    byDriver[driver] = [];
    driverColors.set(driver, DRIVER_COLORS[i % DRIVER_COLORS.length]);
  });

  laps.forEach((lap) => {
    const driver = lap.driver;
    if (!driver || !byDriver[driver]) return;

    const lapNum = lap.lap_number ?? lap.lap ?? 0;
    const delta = lap.pace_delta;
    const isPitLap =
      lap.is_pit_lap ?? lap.pit_lap ?? !!(lap.is_pit_out_lap || lap.is_in_lap);
    const compound = lap.compound ?? null;
    const tyreAge = lap.lap_index_in_stint ?? null;
    const trackStatus =
      lap.state_label && lap.state_label !== "GREEN"
        ? lap.state_label
        : lap.is_track_green === false
          ? "Yellow/SC"
          : lap.is_track_green === true
            ? "GREEN"
            : lap.state_label ?? "GREEN";

    const point: LapPoint = {
      lap: lapNum,
      delta: delta != null ? Number(delta) : null,
      isPitLap: !!isPitLap,
      compound,
      tyreAge,
      trackStatus,
      driver,
    };
    byDriver[driver].push(point);
  });

  const series: DriverSeries[] = Object.entries(byDriver).map(([driver, points]) => ({
    driver,
    points: points.sort((a, b) => a.lap - b.lap),
  }));

  const lapSet = new Set<number>();
  series.forEach((s) => s.points.forEach((p) => lapSet.add(p.lap)));
  const lapsSorted = Array.from(lapSet).sort((a, b) => a - b);

  const rechartsData = lapsSorted.map((lap) => {
    const row: { lap: number; [driver: string]: number | undefined } = { lap };
    series.forEach((s) => {
      const pt = s.points.find((p) => p.lap === lap);
      row[s.driver] = pt?.delta ?? undefined;
    });
    return row;
  });

  const pointLookup = new Map<string, LapPoint>();
  series.forEach((s) =>
    s.points.forEach((p) => pointLookup.set(pointKey(p.lap, s.driver), p))
  );

  return { series, rechartsData, pointLookup, driverColors };
}

/** Stroke color for dot ring by track state (SC/RED/VSC/YELLOW distinct from green) */
function getDotTrackStroke(trackStatus: string | null | undefined): string | null {
  if (!trackStatus || trackStatus === "GREEN") return null;
  const t = String(trackStatus).toUpperCase();
  if (t === "RED") return "rgba(239,68,68,0.8)";
  if (t === "SC") return "rgba(251,191,36,0.8)";
  if (t === "VSC") return "rgba(96,165,250,0.8)";
  if (t.startsWith("YELLOW")) return "rgba(245,158,11,0.8)";
  return null;
}

/** Custom dot: no dot if delta is null; pit lap = radius 6, else 3; track state = ring color */
function CustomDot(props: {
  cx?: number;
  cy?: number;
  payload?: { lap: number; [k: string]: number | undefined };
  dataKey?: string;
  pointLookup: Map<string, LapPoint>;
  color: string;
  isSelected: boolean;
}) {
  const { cx, cy, payload, dataKey, pointLookup, color, isSelected } = props;
  if (cx == null || cy == null || !payload || !dataKey) return null;
  const lap = payload.lap;
  const delta = payload[dataKey];
  if (delta == null) return null;

  const key = pointKey(lap, dataKey);
  const point = pointLookup.get(key);
  const isPitLap = point?.isPitLap ?? false;
  const trackStroke = getDotTrackStroke(point?.trackStatus);
  const r = isPitLap ? 6 : 3;
  const opacity = isSelected ? 1 : 0.4;

  return (
    <g>
      {isPitLap && (
        <circle
          cx={cx}
          cy={cy}
          r={r + 2}
          fill="none"
          stroke={color}
          strokeWidth={1}
          opacity={opacity * 0.6}
        />
      )}
      {trackStroke && !isPitLap && (
        <circle
          cx={cx}
          cy={cy}
          r={r + 1.5}
          fill="none"
          stroke={trackStroke}
          strokeWidth={1.5}
          opacity={opacity}
        />
      )}
      {trackStroke && isPitLap && (
        <circle
          cx={cx}
          cy={cy}
          r={r + 2.5}
          fill="none"
          stroke={trackStroke}
          strokeWidth={1}
          opacity={opacity * 0.7}
        />
      )}
      <circle
        cx={cx}
        cy={cy}
        r={r}
        fill={color}
        fillOpacity={opacity}
        stroke="none"
      />
    </g>
  );
}

/** Badge class for track state in tooltip (dark theme) */
function getTrackBadgeClass(trackStatus: string | null | undefined): string {
  if (!trackStatus || trackStatus === "GREEN") return "bg-emerald-500/20 text-emerald-300 border-emerald-500/40";
  const t = String(trackStatus).toUpperCase();
  if (t === "RED") return "bg-red-500/25 text-red-200 border-red-500/40";
  if (t === "SC") return "bg-white/20 text-gray-200 border-white/30";
  if (t === "VSC") return "bg-blue-500/25 text-blue-200 border-blue-500/40";
  if (t.startsWith("YELLOW")) return "bg-amber-500/25 text-amber-200 border-amber-500/40";
  return "bg-white/10 text-[var(--color-text-muted)] border-[var(--color-border)]";
}

/** Custom tooltip: Driver, Lap, Delta (±, 2 decimals), Compound, TyreAge, Pit, Track (badge); dark-mode readable */
function PaceDeltaTooltipContent(props: {
  active?: boolean;
  payload?: Payload<number, string>[];
  label?: number;
  pointLookup: Map<string, LapPoint>;
}) {
  const { active, payload, label, pointLookup } = props;
  if (!active || !payload?.length || label == null) return null;

  const lap = Number(label);
  const items = payload.filter((p) => p.dataKey && p.value != null);
  if (items.length === 0) return null;

  return (
    <div
      className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-2.5 shadow-xl"
      style={{
        background: "var(--color-bg-card)",
        border: "1px solid var(--color-border)",
      }}
    >
      <div className="mb-1.5 text-xs font-semibold text-[var(--color-text-default)]">
        Lap {lap}
      </div>
      <div className="space-y-1.5">
        {items.map((p) => {
          const driver = String(p.dataKey);
          const delta = Number(p.value);
          const key = pointKey(lap, driver);
          const point = pointLookup.get(key);
          const compound = point?.compound ?? "—";
          const tyreAge = point?.tyreAge ?? "—";
          const pit = point?.isPitLap ? "Yes" : "No";
          const trackStatus = point?.trackStatus ?? "GREEN";
          const sign = delta >= 0 ? "+" : "";
          return (
            <div
              key={driver}
              className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs"
            >
              <span className="text-[var(--color-text-muted)]">Driver</span>
              <span className="font-medium text-[var(--color-text-default)]">{driver}</span>
              <span className="text-[var(--color-text-muted)]">Delta</span>
              <span className="text-[var(--color-text-default)]">
                {sign}{delta.toFixed(2)}s
              </span>
              <span className="text-[var(--color-text-muted)]">Compound</span>
              <span className="text-[var(--color-text-default)]">{compound}</span>
              <span className="text-[var(--color-text-muted)]">Tyre age</span>
              <span className="text-[var(--color-text-default)]">{String(tyreAge)}</span>
              <span className="text-[var(--color-text-muted)]">Pit lap</span>
              <span className="text-[var(--color-text-default)]">{pit}</span>
              <span className="text-[var(--color-text-muted)]">Track</span>
              <span className="text-[var(--color-text-default)]">
                <span
                  className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-medium ${getTrackBadgeClass(trackStatus)}`}
                >
                  {String(trackStatus)}
                </span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function PaceDeltaChart({
  lapsWithDelta,
  title = "Pace delta vs race median (clean laps)",
  colorByCompound = false,
  selectedDrivers,
  height = 360,
  embedded = false,
}: PaceDeltaChartProps) {
  const allDrivers = useMemo(
    () => [...new Set(lapsWithDelta.map((l) => l.driver).filter(Boolean))].slice(0, MAX_DRIVERS),
    [lapsWithDelta]
  );
  const selectedSet = useMemo(
    () =>
      selectedDrivers === undefined
        ? new Set(allDrivers)
        : new Set(selectedDrivers),
    [selectedDrivers, allDrivers]
  );

  const { series, rechartsData, pointLookup, driverColors } = useMemo(
    () => transformToSeriesShowAll(lapsWithDelta),
    [lapsWithDelta]
  );

  const chartContent = (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={rechartsData}
          margin={{ top: 8, right: 16, left: 8, bottom: 8 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
          <XAxis
            dataKey="lap"
            type="number"
            domain={["dataMin", "dataMax"]}
            stroke="#94a3b8"
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            tickFormatter={(v) => `Lap ${v}`}
          />
          <YAxis
            stroke="#94a3b8"
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            tickFormatter={(v) => `${v.toFixed(2)}s`}
            label={{
              value: "Pace delta (s)",
              angle: -90,
              position: "insideLeft",
              fill: "#94a3b8",
              fontSize: 11,
            }}
          />
          <Tooltip
            content={(props) => (
              <PaceDeltaTooltipContent {...props} pointLookup={pointLookup} />
            )}
            cursor={{ stroke: "rgba(255,255,255,0.2)", strokeWidth: 1 }}
          />
          <ReferenceLine y={0} stroke="rgba(255,255,255,0.25)" strokeDasharray="2 2" />
          {series
            .filter((s) => selectedSet.has(s.driver))
            .map((s) => {
              const color = driverColors.get(s.driver) ?? "#94a3b8";
              return (
                <Line
                  key={s.driver}
                  type="monotone"
                  dataKey={s.driver}
                  name={s.driver}
                  stroke={color}
                  strokeWidth={1.5}
                  strokeDasharray="4 4"
                  strokeOpacity={1}
                  dot={(dotProps) => (
                    <CustomDot
                      {...dotProps}
                      dataKey={s.driver}
                      pointLookup={pointLookup}
                      color={color}
                      isSelected
                    />
                  )}
                  connectNulls
                  isAnimationActive={false}
                />
              );
            })}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );

  if (embedded) return chartContent;

  return (
    <Card className="border-[var(--color-border)] bg-[var(--color-bg-card)]">
      <CardHeader>
        <CardTitle className="text-[var(--color-text-default)]">{title}</CardTitle>
      </CardHeader>
      <CardContent>{chartContent}</CardContent>
    </Card>
  );
}
