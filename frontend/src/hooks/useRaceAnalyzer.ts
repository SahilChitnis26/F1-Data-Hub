import { useState, useEffect, useCallback } from "react";
import type { RaceAnalyzerResponse } from "@/types/api";

const API_BASE = "/api";

export interface UseRaceAnalyzerOptions {
  season: number;
  round: number;
  /** Set to true to bypass backend cache */
  refresh?: boolean;
}

export interface UseRaceAnalyzerResult {
  data: RaceAnalyzerResponse | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/**
 * Fetches race analyzer data from /api/race_analyzer/{season}/{round}.
 * Handles loading and error states. Does not embed fetch inside chart components.
 */
export function useRaceAnalyzer({
  season,
  round,
  refresh = false,
}: UseRaceAnalyzerOptions): UseRaceAnalyzerResult {
  const [data, setData] = useState<RaceAnalyzerResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(() => {
    setLoading(true);
    setError(null);
    const url = `${API_BASE}/race_analyzer/${season}/${round}${refresh ? "?refresh=1" : ""}`;
    fetch(url)
      .then((res) => {
        if (!res.ok) {
          return res.json().then((err) => {
            throw new Error(err.detail ?? "Failed to load race analyzer");
          });
        }
        return res.json();
      })
      .then((json: RaceAnalyzerResponse) => {
        setData(json);
        setLoading(false);
      })
      .catch((e: Error) => {
        setError(e.message ?? "Failed to fetch");
        setLoading(false);
      });
  }, [season, round, refresh]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refetch: fetchData };
}
