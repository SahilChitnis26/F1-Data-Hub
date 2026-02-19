import {
  useRef,
  useEffect,
  useState,
  useCallback,
  useMemo,
} from "react";
import { DRIVER_COLORS } from "@/components/charts/PaceDeltaChart";
import { cn } from "@/lib/utils";
import {
  getOrientationForTrack,
  loadDevOrientation,
  saveDevOrientation,
  formatOverrideJson,
  type TrackOrientation,
} from "@/lib/trackOrientation";
import { buildTrackTransform } from "@/lib/trackTransform";

const PAD = 48;
const TRACK_LINE_WIDTH = 4;
const DRIVER_LINE_WIDTH = 2;
const DOT_R = 5;
const FIXED_HEIGHT = 420;

type NormalizedData = {
  track: { x: number[]; y: number[] } | null;
  drivers: Record<string, { x: number[]; y: number[] }>;
};

function hasNaN(arr: number[]): boolean {
  return arr.some((v) => typeof v !== "number" || Number.isNaN(v));
}

function isEmptyOrNaN(x: number[], y: number[]): boolean {
  return (
    !x?.length ||
    !y?.length ||
    x.length !== y.length ||
    hasNaN(x) ||
    hasNaN(y)
  );
}

/**
 * Detect response shape and normalize to { track, drivers }.
 * A) { track: { x, y }, drivers: Record<string, { x, y }> }
 * B) { track_x, track_y, driver_traces: Array<{ driver, x, y }> }
 * C) { meta, timeline_ms, series } (current backend) → drivers = series, track = first driver path
 */
function normalizeResponse(json: unknown): NormalizedData | null {
  if (!json || typeof json !== "object") return null;
  const o = json as Record<string, unknown>;

  // Shape A
  const trackA = o.track as { x?: number[]; y?: number[] } | undefined;
  const driversA = o.drivers as Record<string, { x?: number[]; y?: number[] }> | undefined;
  if (
    trackA &&
    Array.isArray(trackA.x) &&
    Array.isArray(trackA.y) &&
    driversA &&
    typeof driversA === "object"
  ) {
    const drivers: Record<string, { x: number[]; y: number[] }> = {};
    for (const [k, v] of Object.entries(driversA)) {
      if (v && Array.isArray(v.x) && Array.isArray(v.y))
        drivers[k] = { x: v.x, y: v.y };
    }
    return {
      track: { x: trackA.x, y: trackA.y },
      drivers,
    };
  }

  // Shape B
  const trackX = o.track_x as number[] | undefined;
  const trackY = o.track_y as number[] | undefined;
  const traces = o.driver_traces as Array<{
    driver?: string;
    x?: number[];
    y?: number[];
  }> | undefined;
  if (Array.isArray(trackX) && Array.isArray(trackY) && Array.isArray(traces)) {
    const drivers: Record<string, { x: number[]; y: number[] }> = {};
    for (const t of traces) {
      const name = t.driver != null ? String(t.driver) : "";
      if (name && Array.isArray(t.x) && Array.isArray(t.y))
        drivers[name] = { x: t.x, y: t.y };
    }
    return {
      track:
        trackX.length && trackY.length
          ? { x: trackX, y: trackY }
          : null,
      drivers,
    };
  }

  // Shape C (current backend): meta, timeline_ms, series
  const series = o.series as Record<string, { x?: number[]; y?: number[] }> | undefined;
  if (series && typeof series === "object") {
    const drivers: Record<string, { x: number[]; y: number[] }> = {};
    let firstTrack: { x: number[]; y: number[] } | null = null;
    const keys = Object.keys(series);
    for (const k of keys) {
      const v = series[k];
      if (v && Array.isArray(v.x) && Array.isArray(v.y)) {
        drivers[k] = { x: v.x, y: v.y };
        if (!firstTrack) firstTrack = { x: v.x, y: v.y };
      }
    }
    return {
      track: firstTrack,
      drivers,
    };
  }

  return null;
}

export interface TrackMapProps {
  /** Full URL for GET /api/races/:raceId/replay/track?drivers=...&lap_start=...&lap_end=...&sample_hz=... */
  endpointUrl: string;
  className?: string;
}

export function TrackMap({ endpointUrl, className }: TrackMapProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<NormalizedData | null>(null);
  const [rawKeys, setRawKeys] = useState<string[] | null>(null);
  const [trackKey, setTrackKey] = useState<string>("");
  const [devOverride, setDevOverride] = useState<TrackOrientation | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sizeRef = useRef({ width: 0, height: 0 });
  const loggedOnceRef = useRef(false);

  // Fetch once on mount and when endpointUrl changes
  useEffect(() => {
    if (!endpointUrl || endpointUrl.trim() === "") {
      setLoading(false);
      setError(null);
      setData(null);
      setRawKeys(null);
      setTrackKey("");
      setDevOverride(null);
      return;
    }

    setLoading(true);
    setError(null);
    setData(null);
    setRawKeys(null);
    setTrackKey("");
    setDevOverride(null);
    loggedOnceRef.current = false;

    fetch(endpointUrl)
      .then((res) => {
        if (!res.ok) {
          return res.json().then((err: { detail?: string }) => {
            throw new Error(err.detail ?? `HTTP ${res.status}`);
          });
        }
        return res.json();
      })
      .then((json: unknown) => {
        if (import.meta.env.DEV && !loggedOnceRef.current) {
          console.log("[TrackMap] raw JSON (once):", json);
          loggedOnceRef.current = true;
        }

        const normalized = normalizeResponse(json);
        if (normalized) {
          const meta = (json as Record<string, unknown>)?.meta as Record<string, unknown> | undefined;
          const key = (meta?.track_key ?? meta?.race_id) ?? "unknown";
          setTrackKey(String(key));
          if (import.meta.env.DEV) {
            setDevOverride(loadDevOrientation(String(key)));
            const { track, drivers } = normalized;
            if (track && isEmptyOrNaN(track.x, track.y))
              console.warn("[TrackMap] track x/y empty or contains NaN");
            for (const [name, d] of Object.entries(drivers)) {
              if (isEmptyOrNaN(d.x, d.y))
                console.warn(
                  `[TrackMap] driver "${name}" x/y empty or contains NaN`
                );
            }
          }
          setData(normalized);
        } else {
          const keys = typeof json === "object" && json !== null
            ? Object.keys(json as object)
            : [];
          setRawKeys(keys);
          setError(`Unexpected response shape. Keys: ${keys.join(", ") || "(none)"}`);
        }
        setLoading(false);
      })
      .catch((e: Error) => {
        setError(e.message ?? "Failed to fetch");
        setLoading(false);
      });
  }, [endpointUrl]);

  const orientation = useMemo(
    () => getOrientationForTrack(trackKey, devOverride),
    [trackKey, devOverride]
  );

  const draw = useCallback(
    (ctx: CanvasRenderingContext2D, w: number, h: number) => {
      const nd = data;
      if (!nd) return;

      const { track, drivers } = nd;
      const driverEntries = Object.entries(drivers);
      const hasAny =
        (track && track.x.length > 0) ||
        driverEntries.some(([, d]) => d.x.length > 0);

      if (!hasAny) {
        ctx.strokeStyle = "rgba(255,100,100,0.6)";
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.moveTo(PAD, PAD);
        ctx.lineTo(w - PAD, h - PAD);
        ctx.moveTo(w - PAD, PAD);
        ctx.lineTo(PAD, h - PAD);
        ctx.stroke();
        return;
      }

      const transform = buildTrackTransform({
        track,
        drivers,
        orientation,
        width: w,
        height: h,
        padding: PAD,
      });
      if (!transform) return;
      const { toCanvas } = transform;

      // Muted grid
      ctx.strokeStyle = "rgba(255,255,255,0.06)";
      ctx.lineWidth = 1;
      const gridStep = 40;
      for (let gx = PAD; gx <= w - PAD; gx += gridStep) {
        ctx.beginPath();
        ctx.moveTo(gx, PAD);
        ctx.lineTo(gx, h - PAD);
        ctx.stroke();
      }
      for (let gy = PAD; gy <= h - PAD; gy += gridStep) {
        ctx.beginPath();
        ctx.moveTo(PAD, gy);
        ctx.lineTo(w - PAD, gy);
        ctx.stroke();
      }

      // Track centerline (shared pipeline)
      if (track && track.x.length > 0 && track.y.length > 0) {
        ctx.strokeStyle = "rgba(255,255,255,0.2)";
        ctx.lineWidth = TRACK_LINE_WIDTH;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.beginPath();
        const p0 = toCanvas(track.x[0], track.y[0]);
        ctx.moveTo(p0.x, p0.y);
        for (let i = 1; i < track.x.length; i++) {
          const p = toCanvas(track.x[i], track.y[i]);
          ctx.lineTo(p.x, p.y);
        }
        ctx.stroke();
      }

      // Driver traces (shared pipeline)
      driverEntries.forEach(([driver], idx) => {
        const d = drivers[driver];
        if (!d?.x?.length || !d.y?.length) return;
        const color = DRIVER_COLORS[idx % DRIVER_COLORS.length];
        ctx.strokeStyle = color;
        ctx.lineWidth = DRIVER_LINE_WIDTH;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.beginPath();
        const p0 = toCanvas(d.x[0], d.y[0]);
        ctx.moveTo(p0.x, p0.y);
        for (let i = 1; i < d.x.length; i++) {
          const p = toCanvas(d.x[i], d.y[i]);
          ctx.lineTo(p.x, p.y);
        }
        ctx.stroke();
      });

      // Driver dots at last sample (shared pipeline)
      driverEntries.forEach(([driver], idx) => {
        const d = drivers[driver];
        if (!d?.x?.length || !d.y?.length) return;
        const i = d.x.length - 1;
        const p = toCanvas(d.x[i], d.y[i]);
        const color = DRIVER_COLORS[idx % DRIVER_COLORS.length];
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(p.x, p.y, DOT_R, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = "rgba(0,0,0,0.4)";
        ctx.lineWidth = 1;
        ctx.stroke();
      });
    },
    [data, orientation]
  );

  useEffect(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const ro = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const { width, height } = entry.contentRect;
      const w = Math.max(1, Math.floor(width));
      const h = Math.max(1, Math.floor(height));
      if (import.meta.env.DEV && (w === 0 || h === 0)) {
        console.warn("[TrackMap] canvas width or height is 0", { w, h });
      }
      const dpr = window.devicePixelRatio ?? 1;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      sizeRef.current = { width: w, height: h };
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      draw(ctx, w, h);
    });

    ro.observe(container);
    const { width: w, height: h } = sizeRef.current;
    if (w > 0 && h > 0) draw(ctx, w, h);
    return () => ro.disconnect();
  }, [draw, data]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    const { width: w, height: h } = sizeRef.current;
    if (ctx && w > 0 && h > 0 && data) draw(ctx, w, h);
  }, [data, draw]);

  useEffect(() => {
    if (import.meta.env.DEV && trackKey && devOverride !== null) {
      saveDevOrientation(trackKey, devOverride);
    }
  }, [trackKey, devOverride]);

  const handleCopyOverrideJson = useCallback(() => {
    const str = formatOverrideJson(trackKey, orientation);
    console.log("[TrackMap] Override JSON:", str);
    const full = `  ${str},\n`;
    void navigator.clipboard.writeText(full).then(() => {
      if (import.meta.env.DEV) console.log("[TrackMap] Copied to clipboard:", full);
    });
  }, [trackKey, orientation]);

  const driverList = useMemo(
    () => (data?.drivers ? Object.keys(data.drivers).sort() : []),
    [data?.drivers]
  );

  const hasValidData =
    data &&
    ((data.track && data.track.x.length > 0) ||
      Object.values(data.drivers).some((d) => d.x.length > 0));

  return (
    <div
      className={cn(
        "rounded-2xl border border-[var(--border)] bg-[var(--panel)] overflow-hidden",
        className
      )}
    >
      <div
        ref={containerRef}
        className="relative w-full bg-[var(--bg)]"
        style={{ height: FIXED_HEIGHT }}
      >
        <canvas
          ref={canvasRef}
          className="block w-full h-full"
          style={{ width: "100%", height: FIXED_HEIGHT }}
        />
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-[var(--panel)]/80 text-[var(--color-text-muted)]">
            Loading…
          </div>
        )}
        {error && !loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 px-4 py-6 bg-[var(--panel)]/90 text-[var(--color-tertiary)] text-sm text-center">
            <span>{error}</span>
            {rawKeys && rawKeys.length > 0 && (
              <code className="text-xs text-[var(--color-text-muted)]">
                Keys: {rawKeys.join(", ")}
              </code>
            )}
          </div>
        )}
        {!loading && !error && !hasValidData && data !== null && (
          <div className="absolute bottom-0 left-0 right-0 py-2 px-4 bg-[var(--panel)]/90 text-center text-[var(--color-text-muted)] text-sm border-t border-[var(--border)]">
            No track or driver data (canvas test visible above)
          </div>
        )}
      </div>
      {import.meta.env.DEV && trackKey && hasValidData && (
        <div className="flex flex-wrap items-center gap-4 px-4 py-2 border-t border-[var(--border)] bg-[var(--panel)]/50 text-xs">
          <span className="font-medium text-[var(--color-text-muted)]">Track orientation (dev)</span>
          <label className="flex items-center gap-2">
            <span className="text-[var(--color-text-muted)]">rotate</span>
            <input
              type="range"
              min={-180}
              max={180}
              value={orientation.rotateDeg}
              onChange={(e) =>
                setDevOverride((prev) => ({
                  ...(prev ?? orientation),
                  rotateDeg: Number(e.target.value),
                }))
              }
              className="w-24"
            />
            <span className="tabular-nums text-[var(--color-text-default)]">{orientation.rotateDeg}°</span>
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={orientation.flipX}
              onChange={() =>
                setDevOverride((prev) => ({
                  ...(prev ?? orientation),
                  flipX: !orientation.flipX,
                }))
              }
            />
            <span className="text-[var(--color-text-muted)]">flipX</span>
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={orientation.flipY}
              onChange={() =>
                setDevOverride((prev) => ({
                  ...(prev ?? orientation),
                  flipY: !orientation.flipY,
                }))
              }
            />
            <span className="text-[var(--color-text-muted)]">flipY</span>
          </label>
          <button
            type="button"
            onClick={handleCopyOverrideJson}
            className="px-2 py-1 rounded bg-[var(--border)] text-[var(--color-text-default)] hover:bg-[var(--border)]/80"
          >
            Copy override JSON
          </button>
        </div>
      )}
      {driverList.length > 0 && hasValidData && (
        <div className="flex flex-wrap items-center gap-3 px-4 py-3 border-t border-[var(--border)]">
          <span className="text-xs font-medium text-[var(--color-text-muted)] uppercase tracking-wider">
            Drivers
          </span>
          {driverList.map((driver, idx) => (
            <span
              key={driver}
              className="flex items-center gap-1.5 text-sm text-[var(--color-text-default)]"
            >
              <span
                className="inline-block w-2.5 h-2.5 rounded-full shrink-0"
                style={{
                  backgroundColor:
                    DRIVER_COLORS[idx % DRIVER_COLORS.length],
                }}
              />
              {driver}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
