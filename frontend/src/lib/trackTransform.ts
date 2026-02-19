/**
 * Shared transform pipeline for TrackMap: same math for track polyline and driver positions.
 * Order: center → rotate → flipX/flipY → uniform scale to fit (padding) → translate to canvas center.
 * Canvas Y increases downward; default flipY in orientation often needed so track is not upside-down.
 */

import type { TrackOrientation } from "./trackOrientation";

export interface TransformParams {
  track: { x: number[]; y: number[] } | null;
  drivers: Record<string, { x: number[]; y: number[] }>;
  orientation: TrackOrientation;
  width: number;
  height: number;
  padding: number;
}

export interface TrackTransformResult {
  toCanvas: (x: number, y: number) => { x: number; y: number };
}

function collectPoints(
  track: { x: number[]; y: number[] } | null,
  drivers: Record<string, { x: number[]; y: number[] }>
): { x: number; y: number }[] {
  const points: { x: number; y: number }[] = [];
  const add = (x: number[], y: number[]) => {
    for (let i = 0; i < x.length && i < y.length; i++) {
      const a = x[i];
      const b = y[i];
      if (typeof a === "number" && typeof b === "number" && !Number.isNaN(a) && !Number.isNaN(b)) {
        points.push({ x: a, y: b });
      }
    }
  };
  if (track) add(track.x, track.y);
  for (const d of Object.values(drivers)) add(d.x, d.y);
  return points;
}

/**
 * Apply steps a–c: center (subtract mean), rotate by rotateDeg, then flipX/flipY.
 * Returns transformed point and updates running bounds.
 */
function applyCenterRotateFlip(
  x: number,
  y: number,
  meanX: number,
  meanY: number,
  orientation: TrackOrientation
): { x: number; y: number } {
  let x1 = x - meanX;
  let y1 = y - meanY;
  const deg = orientation.rotateDeg;
  if (deg !== 0) {
    const rad = (deg * Math.PI) / 180;
    const c = Math.cos(rad);
    const s = Math.sin(rad);
    const x2 = x1 * c - y1 * s;
    const y2 = x1 * s + y1 * c;
    x1 = x2;
    y1 = y2;
  }
  if (orientation.flipX) x1 = -x1;
  if (orientation.flipY) y1 = -y1;
  return { x: x1, y: y1 };
}

/**
 * Build a single transform used for both track line and driver positions.
 * Pipeline: center → rotate → flipX/flipY → bbox + uniform scale to fit with padding → translate to canvas center.
 */
export function buildTrackTransform(params: TransformParams): TrackTransformResult | null {
  const { track, drivers, orientation, width, height, padding } = params;
  const points = collectPoints(track, drivers);
  if (points.length === 0) return null;

  const n = points.length;
  let sumX = 0;
  let sumY = 0;
  for (const p of points) {
    sumX += p.x;
    sumY += p.y;
  }
  const meanX = sumX / n;
  const meanY = sumY / n;

  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const p of points) {
    const t = applyCenterRotateFlip(p.x, p.y, meanX, meanY, orientation);
    minX = Math.min(minX, t.x);
    maxX = Math.max(maxX, t.x);
    minY = Math.min(minY, t.y);
    maxY = Math.max(maxY, t.y);
  }
  const rangeX = maxX - minX || 1;
  const rangeY = maxY - minY || 1;
  const drawW = width - 2 * padding;
  const drawH = height - 2 * padding;
  const scale = Math.min(drawW / rangeX, drawH / rangeY);
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const canvasCenterX = width / 2;
  const canvasCenterY = height / 2;
  const tx = canvasCenterX - cx * scale;
  const ty = canvasCenterY - cy * scale;

  return {
    toCanvas(x: number, y: number) {
      const t = applyCenterRotateFlip(x, y, meanX, meanY, orientation);
      return {
        x: tx + t.x * scale,
        y: ty + t.y * scale,
      };
    },
  };
}
