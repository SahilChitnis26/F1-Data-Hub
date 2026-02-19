import { useState, useEffect, useCallback, useRef } from "react";
import { buildApiUrl } from "@/lib/api";
import type { ReplayTrackResponse } from "@/types/api";

export interface UseReplayTrackOptions {
  season: number;
  round: number;
  drivers: string[];
  lapStart: number;
  lapEnd: number;
  sampleHz?: number;
  /** Only fetch when true (e.g. user clicked Load or has selected drivers) */
  enabled?: boolean;
  refresh?: boolean;
}

export interface UseReplayTrackResult {
  data: ReplayTrackResponse | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/** Stable string for driver list so effect only runs when selection actually changes. */
function driversKey(drivers: string[]): string {
  return drivers.slice().sort().join(",");
}

/**
 * Fetches track replay data from GET /api/races/{race_id}/replay/track.
 * Call with enabled: true when drivers are selected and lap range is valid.
 * Fetches only when raceId, selectedDrivers, lapStart, lapEnd, sampleHz (or enabled/refresh) change.
 */
export function useReplayTrack({
  season,
  round,
  drivers,
  lapStart,
  lapEnd,
  sampleHz = 10,
  enabled = false,
  refresh = false,
}: UseReplayTrackOptions): UseReplayTrackResult {
  const [data, setData] = useState<ReplayTrackResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const lastParamsRef = useRef<UseReplayTrackOptions | null>(null);

  const stableDriversKey = driversKey(drivers);

  useEffect(() => {
    if (!enabled || drivers.length === 0 || lapStart > lapEnd) {
      setLoading(false);
      setData(null);
      setError(null);
      return;
    }

    lastParamsRef.current = {
      season,
      round,
      drivers,
      lapStart,
      lapEnd,
      sampleHz,
      enabled,
      refresh,
    };

    setLoading(true);
    setError(null);
    const raceId = `${season}_${round}`;
    const params = new URLSearchParams({
      drivers: drivers.join(","),
      lap_start: String(lapStart),
      lap_end: String(lapEnd),
      sample_hz: String(sampleHz),
    });
    if (refresh) params.set("refresh", "1");
    const path = `races/${raceId}/replay/track`;
    const url = `${buildApiUrl(path)}?${params}`;
    if (import.meta.env.DEV) {
      console.log("Fetching replay data once...");
    }
    fetch(url)
      .then((res) => {
        if (!res.ok) {
          return res.json().then((err: { detail?: string }) => {
            throw new Error(err.detail ?? "Failed to load replay");
          });
        }
        return res.json();
      })
      .then((json: ReplayTrackResponse) => {
        setData(json);
        setLoading(false);
      })
      .catch((e: Error) => {
        setError(e.message ?? "Failed to fetch replay");
        setLoading(false);
      });
  }, [
    season,
    round,
    stableDriversKey,
    lapStart,
    lapEnd,
    sampleHz,
    enabled,
    refresh,
  ]);

  const refetch = useCallback(() => {
    const p = lastParamsRef.current;
    if (!p || !p.enabled || p.drivers.length === 0 || p.lapStart > p.lapEnd) {
      return;
    }
    setLoading(true);
    setError(null);
    const raceId = `${p.season}_${p.round}`;
    const params = new URLSearchParams({
      drivers: p.drivers.join(","),
      lap_start: String(p.lapStart),
      lap_end: String(p.lapEnd),
      sample_hz: String(p.sampleHz ?? 10),
    });
    if (p.refresh) params.set("refresh", "1");
    const path = `races/${raceId}/replay/track`;
    const url = `${buildApiUrl(path)}?${params}`;
    if (import.meta.env.DEV) {
      console.log("Fetching replay data once...");
    }
    fetch(url)
      .then((res) => {
        if (!res.ok) {
          return res.json().then((err: { detail?: string }) => {
            throw new Error(err.detail ?? "Failed to load replay");
          });
        }
        return res.json();
      })
      .then((json: ReplayTrackResponse) => {
        setData(json);
        setLoading(false);
      })
      .catch((e: Error) => {
        setError(e.message ?? "Failed to fetch replay");
        setLoading(false);
      });
  }, []);

  return { data, loading, error, refetch };
}
