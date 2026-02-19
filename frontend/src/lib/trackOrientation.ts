/**
 * Per-track orientation overrides for TrackMap.
 * track_key is stable: `${year}_${round}` (meta.race_id) or circuitId when available.
 */

export type TrackOrientation = {
  rotateDeg: number;
  flipX: boolean;
  flipY: boolean;
};

export const DEFAULT_TRACK_ORIENTATION: TrackOrientation = {
  rotateDeg: 0,
  flipX: false,
  flipY: true,
};

/** Per-track overrides. Add entries from "Copy override JSON" in dev. */
export const TRACK_ORIENTATION: Record<string, TrackOrientation> = {};

const DEV_STORAGE_PREFIX = "trackOrientation:";

/**
 * Returns orientation for a track: override from TRACK_ORIENTATION, then
 * (in dev) localStorage, then default. Default flipY: true accounts for canvas Y-down.
 */
export function getOrientationForTrack(
  trackKey: string,
  devStored?: TrackOrientation | null
): TrackOrientation {
  const fromRecord = TRACK_ORIENTATION[trackKey];
  if (fromRecord) return fromRecord;
  if (devStored) return devStored;
  return { ...DEFAULT_TRACK_ORIENTATION };
}

/**
 * Dev-only: load orientation from localStorage for track_key.
 */
export function loadDevOrientation(trackKey: string): TrackOrientation | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(DEV_STORAGE_PREFIX + trackKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as TrackOrientation;
    if (
      typeof parsed.rotateDeg === "number" &&
      typeof parsed.flipX === "boolean" &&
      typeof parsed.flipY === "boolean"
    ) {
      return parsed;
    }
  } catch {
    /* ignore */
  }
  return null;
}

/**
 * Dev-only: persist orientation to localStorage for track_key.
 */
export function saveDevOrientation(
  trackKey: string,
  orientation: TrackOrientation
): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(
      DEV_STORAGE_PREFIX + trackKey,
      JSON.stringify(orientation)
    );
  } catch {
    /* ignore */
  }
}

/**
 * Dev-only: build override JSON string for TRACK_ORIENTATION.
 */
export function formatOverrideJson(
  trackKey: string,
  orientation: TrackOrientation
): string {
  return `"${trackKey}": { "rotateDeg": ${orientation.rotateDeg}, "flipX": ${orientation.flipX}, "flipY": ${orientation.flipY} }`;
}
