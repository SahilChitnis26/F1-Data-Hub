import {
  useRef,
  useEffect,
  useState,
  useCallback,
  useMemo,
} from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ColoredCheckbox } from "@/components/ui/colored-checkbox";
import { useReplayTrack } from "@/hooks/useReplayTrack";
import { DRIVER_COLORS } from "@/components/charts/PaceDeltaChart";
import { cn } from "@/lib/utils";

const PAD = 40;
const SPEED_OPTIONS = [0.5, 1, 2, 4] as const;
const SCRUBBER_UPDATE_MS = 150;

function binarySearchIndex(timelineMs: number[], t: number): number {
  if (timelineMs.length === 0) return 0;
  if (t <= timelineMs[0]) return 0;
  if (t >= timelineMs[timelineMs.length - 1]) return timelineMs.length - 1;
  let lo = 0;
  let hi = timelineMs.length - 1;
  while (lo + 1 < hi) {
    const mid = (lo + hi) >> 1;
    if (timelineMs[mid] <= t) lo = mid;
    else hi = mid;
  }
  return lo;
}

function interpolate(
  timelineMs: number[],
  x: number[],
  y: number[],
  t: number
): { x: number; y: number } {
  const i = binarySearchIndex(timelineMs, t);
  if (i >= timelineMs.length - 1) return { x: x[i] ?? 0, y: y[i] ?? 0 };
  const t0 = timelineMs[i];
  const t1 = timelineMs[i + 1];
  const frac = t1 === t0 ? 0 : (t - t0) / (t1 - t0);
  return {
    x: (x[i] ?? 0) + frac * ((x[i + 1] ?? 0) - (x[i] ?? 0)),
    y: (y[i] ?? 0) + frac * ((y[i + 1] ?? 0) - (y[i] ?? 0)),
  };
}

function getDriverColor(driver: string, index: number): string {
  return DRIVER_COLORS[index % DRIVER_COLORS.length];
}

export interface RaceReplayTrackViewProps {
  season: number;
  round: number;
  /** Driver codes from race results (e.g. VER, HAM) */
  availableDrivers: string[];
}

export function RaceReplayTrackView({
  season,
  round,
  availableDrivers,
}: RaceReplayTrackViewProps) {
  const [selectedDrivers, setSelectedDrivers] = useState<Set<string>>(
    new Set()
  );
  const [lapStart, setLapStart] = useState(1);
  const [lapEnd, setLapEnd] = useState(5);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState<number>(1);
  const [scrubberReplayMs, setScrubberReplayMs] = useState(0);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const replayTimeMsRef = useRef(0);
  const lastFrameRef = useRef<number>(0);
  const rafIdRef = useRef<number>(0);
  const scrubberIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const driverList = useMemo(
    () => [...availableDrivers].sort(),
    [availableDrivers]
  );
  const enabled =
    selectedDrivers.size > 0 && lapStart <= lapEnd && lapStart >= 1 && lapEnd >= 1;

  const { data, loading, error, refetch } = useReplayTrack({
    season,
    round,
    drivers: [...selectedDrivers],
    lapStart,
    lapEnd,
    sampleHz: 10,
    enabled,
  });

  const durationMs = useMemo(
    () =>
      data?.timeline_ms?.length
        ? data.timeline_ms[data.timeline_ms.length - 1] ?? 0
        : 0,
    [data?.timeline_ms]
  );
  const meta = data?.meta;
  const timelineMs = data?.timeline_ms ?? [];
  const series = data?.series ?? {};

  const selectAll = useCallback(
    () => setSelectedDrivers(new Set(driverList)),
    [driverList]
  );
  const selectNone = useCallback(() => setSelectedDrivers(new Set()), []);

  useEffect(() => {
    if (!data) {
      replayTimeMsRef.current = 0;
      setScrubberReplayMs(0);
    } else {
      replayTimeMsRef.current = Math.min(
        replayTimeMsRef.current,
        durationMs
      );
      setScrubberReplayMs(replayTimeMsRef.current);
    }
  }, [data, durationMs]);

  useEffect(() => {
    if (!isPlaying) return;
    const id = setInterval(() => {
      setScrubberReplayMs(replayTimeMsRef.current);
    }, SCRUBBER_UPDATE_MS);
    scrubberIntervalRef.current = id;
    return () => {
      if (scrubberIntervalRef.current) {
        clearInterval(scrubberIntervalRef.current);
        scrubberIntervalRef.current = null;
      }
    };
  }, [isPlaying]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data?.series || Object.keys(data.series).length === 0) return;

    const timeline = data.timeline_ms;
    const seriesData = data.series;
    const driverCodes = meta?.drivers ?? Object.keys(seriesData);

    let minX = Infinity,
      maxX = -Infinity,
      minY = Infinity,
      maxY = -Infinity;
    for (const code of driverCodes) {
      const s = seriesData[code];
      if (!s?.x?.length) continue;
      for (let i = 0; i < s.x.length; i++) {
        const x = s.x[i];
        const y = s.y[i];
        if (typeof x === "number" && !Number.isNaN(x)) {
          minX = Math.min(minX, x);
          maxX = Math.max(maxX, x);
        }
        if (typeof y === "number" && !Number.isNaN(y)) {
          minY = Math.min(minY, y);
          maxY = Math.max(maxY, y);
        }
      }
    }
    if (minX === Infinity) minX = 0;
    if (maxX === -Infinity) maxX = 1;
    if (minY === Infinity) minY = 0;
    if (maxY === -Infinity) maxY = 1;
    const rangeX = maxX - minX || 1;
    const rangeY = maxY - minY || 1;

    const dpr = window.devicePixelRatio ?? 1;
    const rect = canvas.getBoundingClientRect();
    const w = Math.max(1, Math.floor(rect.width));
    const h = Math.max(1, Math.floor(rect.height));
    canvas.width = w * dpr;
    canvas.height = h * dpr;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const draw = () => {
      const t = replayTimeMsRef.current;
      ctx.save();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const pad = PAD;
      const drawW = w - 2 * pad;
      const drawH = h - 2 * pad;
      const scaleX = drawW / rangeX;
      const scaleY = drawH / rangeY;
      const scale = Math.min(scaleX, scaleY);
      const tx = pad + (drawW - rangeX * scale) / 2 + (-minX * scale);
      const ty = pad + (drawH - rangeY * scale) / 2 + (-minY * scale);

      const toCanvas = (x: number, y: number) => ({
        x: tx + x * scale,
        y: ty + y * scale,
      });

      const firstDriver = driverCodes[0];
      const firstSeries = firstDriver && seriesData[firstDriver];
      if (firstSeries?.x?.length && firstSeries?.y?.length) {
        ctx.strokeStyle = "rgba(255,255,255,0.12)";
        ctx.lineWidth = 2;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.beginPath();
        const pt0 = toCanvas(firstSeries.x[0], firstSeries.y[0]);
        ctx.moveTo(pt0.x, pt0.y);
        for (let i = 1; i < firstSeries.x.length; i++) {
          const pt = toCanvas(firstSeries.x[i], firstSeries.y[i]);
          ctx.lineTo(pt.x, pt.y);
        }
        ctx.stroke();
      }

      const dotR = 6;
      driverCodes.forEach((code, idx) => {
        const s = seriesData[code];
        if (!s?.x?.length) return;
        const { x, y } = interpolate(timeline, s.x, s.y, t);
        const { x: cx, y: cy } = toCanvas(x, y);
        const color = getDriverColor(code, idx);
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(cx, cy, dotR, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = "rgba(0,0,0,0.4)";
        ctx.lineWidth = 1;
        ctx.stroke();
      });

      ctx.restore();
    };

    const tick = (now: number) => {
      const dt = lastFrameRef.current ? now - lastFrameRef.current : 0;
      lastFrameRef.current = now;
      if (isPlaying && durationMs > 0) {
        replayTimeMsRef.current = Math.min(
          durationMs,
          replayTimeMsRef.current + speed * dt
        );
        if (replayTimeMsRef.current >= durationMs) setIsPlaying(false);
      }
      draw();
      rafIdRef.current = requestAnimationFrame(tick);
    };
    lastFrameRef.current = performance.now();
    rafIdRef.current = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(rafIdRef.current);
    };
  }, [data, meta?.drivers, durationMs, isPlaying, speed]);

  const handleScrub = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const v = Number(e.target.value);
      replayTimeMsRef.current = v;
      setScrubberReplayMs(v);
    },
    []
  );

  const handlePlayPause = useCallback(() => {
    setIsPlaying((p) => !p);
  }, []);

  const handleLoad = useCallback(() => {
    refetch();
  }, [refetch]);

  return (
    <Card className="rounded-2xl border border-[var(--border)] glass-panel overflow-hidden">
      <CardHeader>
        <CardTitle className="text-[var(--color-text-default)]">
          Track Replay
        </CardTitle>
        <CardDescription className="text-[var(--color-text-muted)]">
          Select drivers and lap range, then load to animate positions on the
          circuit. Use play/pause and scrubber to control playback.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-sm font-medium text-[var(--color-text-muted)]">
              Drivers
            </span>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={selectAll}
                className="rounded-lg"
              >
                Select All
              </Button>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={selectNone}
                className="rounded-lg"
              >
                Select None
              </Button>
            </div>
          </div>
          <div
            className={cn(
              "grid gap-2 grid-cols-[repeat(auto-fill,minmax(5rem,1fr))] sm:grid-cols-4 md:grid-cols-5"
            )}
          >
            {driverList.map((driver, i) => (
              <ColoredCheckbox
                key={driver}
                checked={selectedDrivers.has(driver)}
                onCheckedChange={(checked) => {
                  const next = new Set(selectedDrivers);
                  if (checked) next.add(driver);
                  else next.delete(driver);
                  setSelectedDrivers(next);
                }}
                label={driver}
                color={getDriverColor(driver, i)}
              />
            ))}
          </div>
          {driverList.length === 0 && (
            <p className="text-sm text-[var(--color-text-muted)]">
              Load a race (Race Overview or Race Analyzer) to see drivers.
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
            Lap start
            <input
              type="number"
              min={1}
              max={100}
              value={lapStart}
              onChange={(e) => setLapStart(Number(e.target.value) || 1)}
              className="w-16 rounded-lg border border-[var(--border)] bg-[var(--panel)] px-2 py-1.5 text-sm text-[var(--color-text-default)] focus:border-[var(--accent1)]/50 focus:outline-none focus:ring-1 focus:ring-[var(--accent1)]/30"
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
            Lap end
            <input
              type="number"
              min={1}
              max={100}
              value={lapEnd}
              onChange={(e) => setLapEnd(Number(e.target.value) || 1)}
              className="w-16 rounded-lg border border-[var(--border)] bg-[var(--panel)] px-2 py-1.5 text-sm text-[var(--color-text-default)] focus:border-[var(--accent1)]/50 focus:outline-none focus:ring-1 focus:ring-[var(--accent1)]/30"
            />
          </label>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={handleLoad}
            disabled={!enabled || loading}
            className="rounded-lg"
          >
            {loading ? "Loading…" : "Load replay"}
          </Button>
        </div>

        {loading && (
          <div className="rounded-xl border border-[var(--border)] bg-[var(--panel)]/50 px-4 py-8 text-center text-sm text-[var(--color-text-muted)]">
            Loading replay data…
          </div>
        )}
        {error && (
          <div className="rounded-xl border-l-4 border-[var(--color-tertiary)] bg-[var(--panel)]/50 px-5 py-4 text-center text-[var(--color-tertiary)]">
            {error}
          </div>
        )}
        {data?.supported === false && (
          <div className="rounded-xl border border-[var(--color-quaternary)]/50 bg-[var(--panel)]/50 py-4 text-center text-amber-200 text-sm">
            {data.message ?? "Replay not available for this race (e.g. no telemetry)."}
          </div>
        )}

        {data && Object.keys(series).length > 0 && (
          <>
            <div className="flex flex-wrap items-center gap-4">
              <Button
                type="button"
                variant="default"
                size="sm"
                onClick={handlePlayPause}
                className="rounded-lg"
              >
                {isPlaying ? "Pause" : "Play"}
              </Button>
              <label className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
                Speed
                <select
                  value={speed}
                  onChange={(e) => setSpeed(Number(e.target.value))}
                  className="rounded-lg border border-[var(--border)] bg-[var(--panel)] px-2 py-1.5 text-sm text-[var(--color-text-default)] focus:border-[var(--accent1)]/50 focus:outline-none focus:ring-1 focus:ring-[var(--accent1)]/30"
                >
                  {SPEED_OPTIONS.map((s) => (
                    <option key={s} value={s}>
                      {s}x
                    </option>
                  ))}
                </select>
              </label>
              <div className="flex-1 min-w-[120px] flex items-center gap-2">
                <input
                  type="range"
                  min={0}
                  max={durationMs}
                  step={Math.max(1, Math.floor(durationMs / 500))}
                  value={scrubberReplayMs}
                  onChange={handleScrub}
                  className="flex-1 h-2 rounded-full appearance-none bg-[var(--panel)] accent-[var(--accent1)]"
                />
                <span className="text-xs text-[var(--color-text-muted)] tabular-nums w-14">
                  {(scrubberReplayMs / 1000).toFixed(1)}s
                </span>
              </div>
            </div>
            <div className="rounded-xl border border-[var(--border)] bg-[var(--panel)]/30 overflow-hidden">
              <div className="h-[440px] sm:h-[600px] w-full">
                <canvas
                  ref={canvasRef}
                  className="w-full h-full block bg-[var(--bg)]"
                  style={{ width: "100%", height: "100%" }}
                />
              </div>
              {/* Driver legend in dedicated footer so it does not overlap the map */}
              {(() => {
                const legendDrivers = (meta?.drivers ?? Object.keys(series)) as string[];
                return legendDrivers.length > 0 ? (
                  <div
                    className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 border-t border-[var(--border)] bg-[var(--panel)]/50"
                    aria-label="Driver legend"
                  >
                    <span className="text-xs font-medium text-[var(--color-text-muted)] uppercase tracking-wider">
                      Drivers
                    </span>
                    {legendDrivers.map((code, idx) => (
                      <span
                        key={code}
                        className="flex items-center gap-1.5 text-sm text-[var(--color-text-default)]"
                      >
                        <span
                          className="inline-block w-2.5 h-2.5 rounded-full shrink-0"
                          style={{ backgroundColor: getDriverColor(code, idx) }}
                        />
                        {code}
                      </span>
                    ))}
                  </div>
                ) : null;
              })()}
            </div>
          </>
        )}

        {enabled && !loading && !error && !data && (
          <div className="rounded-xl border border-dashed border-[var(--border)] bg-[var(--panel)]/50 px-4 py-8 text-center text-sm text-[var(--color-text-muted)]">
            Click “Load replay” to fetch track positions.
          </div>
        )}
        {!enabled && !data && driverList.length > 0 && (
          <div className="rounded-xl border border-dashed border-[var(--border)] bg-[var(--panel)]/50 px-4 py-6 text-center text-sm text-[var(--color-text-muted)]">
            Select at least one driver and ensure lap start ≤ lap end, then click “Load replay”.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
