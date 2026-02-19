import { useState, useEffect, useCallback } from "react";
import type { RaceResultsResponse } from "@/types/api";

const API_BASE = "/api";

export type RaceResultsView = "finish" | "performance";

export interface UseRaceResultsOptions {
  season: number;
  round: number;
  /** Which view: finish position (default) or performance score */
  view: RaceResultsView;
}

export interface UseRaceResultsResult {
  data: RaceResultsResponse | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/**
 * Fetches race results from /api/race/{season}/{round} (finish) or
 * /api/race/{season}/{round}/performance (performance view).
 */
export function useRaceResults({
  season,
  round,
  view,
}: UseRaceResultsOptions): UseRaceResultsResult {
  const [data, setData] = useState<RaceResultsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(() => {
    setLoading(true);
    setError(null);
    const path =
      view === "performance"
        ? `${API_BASE}/race/${season}/${round}/performance`
        : `${API_BASE}/race/${season}/${round}`;
    fetch(path)
      .then((res) => {
        if (!res.ok) {
          return res.json().then((err) => {
            throw new Error(err.detail ?? "Failed to fetch race data");
          });
        }
        return res.json();
      })
      .then((json: RaceResultsResponse) => {
        setData(json);
        setLoading(false);
      })
      .catch((e: Error) => {
        setError(e.message ?? "Failed to fetch");
        setLoading(false);
      });
  }, [season, round, view]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refetch: fetchData };
}
