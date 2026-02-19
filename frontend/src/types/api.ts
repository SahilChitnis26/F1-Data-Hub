/**
 * API response types (aligned with backend api.py).
 * Used by useRaceAnalyzer and useRaceResults.
 */

export interface RaceMeta {
  name: string;
  season: number;
  round: number;
}

/** Track state categories (mutually exclusive; pit is separate). API returns short form. */
export type TrackStateType =
  | "GREEN"
  | "YELLOW"
  | "SC"
  | "VSC"
  | "RED";

/** Single lap from /api/race_analyzer laps array */
export interface LapRecord {
  driver?: string;
  team?: string;
  lap?: number;
  lap_number?: number;
  lap_time_s?: number | null;
  compound?: string | null;
  stint?: number | null;
  pit_lap?: boolean | null;
  is_pit_lap?: boolean | null;
  /** Track state: GREEN | YELLOW | SC | VSC | RED */
  track_state?: TrackStateType | string | null;
  /** Sector numbers for yellow (e.g. [1,2,3]) */
  yellow_sectors?: number[] | null;
  /** Display label: GREEN | SC | VSC | RED | YELLOW S1 | YELLOW S1+S2 etc. */
  state_label?: string | null;
}

/** Lap with pace_delta from computed.laps_with_delta */
export interface LapWithDelta extends LapRecord {
  pace_delta?: number | null;
  lap_index_in_stint?: number | null;
  delta_to_stint_avg?: number | null;
}

export interface StintSummaryRow {
  driver?: string;
  team?: string;
  stint?: number;
  compound?: string;
  laps_in_stint?: number;
  avg_lap_time?: number | null;
  fastest_lap_time?: number | null;
  std_dev?: number | null;
  degradation_slope_sec_per_lap?: number | null;
  avg_pace_delta?: number | null;
}

export interface StintRange {
  driver: string;
  stint: number;
  compound?: string;
  start_lap: number;
  end_lap: number;
  length_laps: number;
}

export interface RaceAnalyzerComputed {
  laps_with_delta?: LapWithDelta[];
  stint_summary?: StintSummaryRow[];
  stint_ranges?: StintRange[];
  insights?: string[];
  results_score?: unknown[];
  execution_score?: unknown[];
  composite_score?: unknown[];
}

/** Full /api/race_analyzer/{season}/{round} response */
export interface RaceAnalyzerResponse {
  supported?: boolean;
  message?: string;
  race_meta?: RaceMeta;
  laps?: LapRecord[];
  computed?: RaceAnalyzerComputed;
}

/** Race result row from /api/race or /api/race/.../performance */
export interface RaceResultRow {
  season?: number;
  round?: number;
  raceName?: string;
  driver: string;
  constructor: string;
  grid: number | string;
  Finish: number;
  status: string;
  time: string;
  points: number | string;
  fastest_lap?: string;
  Performance?: number;
  has_fastest_lap?: boolean;
  dnf_reason?: string;
  dnf_lap?: number | null;
}

export interface RaceInfo {
  season: number;
  round: number;
  raceName: string;
}

/** /api/race/{season}/{round} or /api/race/{season}/{round}/performance response */
export interface RaceResultsResponse {
  race_info: RaceInfo;
  results: RaceResultRow[];
}

/** /api/races/{race_id}/replay/track response */
export interface ReplayTrackMeta {
  race_id: string;
  /** Stable key for per-track orientation overrides (e.g. year_round or circuitId) */
  track_key?: string;
  drivers: string[];
  lap_start: number;
  lap_end: number;
  sample_hz: number;
  time_unit: string;
  coord_unit: string;
}

export interface ReplayTrackResponse {
  meta: ReplayTrackMeta;
  timeline_ms: number[];
  series: Record<string, { x: number[]; y: number[] }>;
  /** Present when session/telemetry not supported */
  supported?: boolean;
  message?: string;
}
