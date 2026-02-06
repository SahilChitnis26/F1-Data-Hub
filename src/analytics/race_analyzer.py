"""
Race analyzer: pace delta vs race-median (clean laps), stint summary, execution score, and deterministic insights.
Uses only valid lap times; optional outlier removal per stint.
"""
from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np
import pandas as pd

_log = logging.getLogger(__name__)
# One-time debug: count laps per track state to verify non-green states (set to True to enable)
_TRACK_STATE_DEBUG_LOG = False
_track_state_debug_logged: bool = False

from ..scoring.execution_score import (
    attach_pace_delta,
    build_clean_laps,
    calculate_execution_score,
    compute_expected_pace,
    clean_laps_mask,
    expected_pace_rolling,
)

# Minimum laps in a stint to compute degradation slope meaningfully
MIN_LAPS_FOR_DEGRADATION = 3
# Outlier threshold: drop laps > mean + OUTLIER_STD * std within driver stint
OUTLIER_STD = 3.0
# Minimum laps in stint for "best tire management" insight
MIN_LAPS_FOR_INSIGHT_STINT = 5


def _valid_laps(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to rows with valid numeric lap_time_s."""
    if "lap_time_s" not in df.columns or df.empty:
        return df.copy()
    return df.loc[df["lap_time_s"].notna() & pd.to_numeric(df["lap_time_s"], errors="coerce").notna()].copy()


def _tyre_regime_from_compound(df: pd.DataFrame) -> pd.Series:
    """Derive tyre_regime (SLICK vs WET) from compound. SLICK=Soft/Medium/Hard, WET=Intermediate/Wet."""
    if "tyre_regime" in df.columns:
        return df["tyre_regime"]
    if "compound" not in df.columns:
        return pd.Series("SLICK", index=df.index)
    comp = df["compound"].astype(str).str.upper()
    return np.where(comp.isin(["INTERMEDIATE", "WET"]), "WET", "SLICK")


def _drop_stint_outliers(df: pd.DataFrame) -> pd.DataFrame:
    """Within each (driver, stint), drop laps with lap_time_s > mean + OUTLIER_STD * std."""
    if df.empty or "lap_time_s" not in df.columns:
        return df
    out = []
    for (driver, stint), grp in df.groupby(["driver", "stint"], dropna=False):
        t = pd.to_numeric(grp["lap_time_s"], errors="coerce")
        mu = t.mean()
        std = t.std()
        if std is None or (std == 0 or math.isnan(std)):
            out.append(grp)
        else:
            mask = t <= mu + OUTLIER_STD * std
            out.append(grp.loc[mask])
    return pd.concat(out, ignore_index=True) if out else df.copy()


def expected_lap_time_by_lap_regime(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each (lap_number, tyre_regime), expected lap time = rolling median of clean laps
    in window [l-k, l+k] (k=2, min 8 samples; else k=4). Lap 1 is excluded from computation.
    Slick and wet have separate baselines; regimes never mixed. Wrapper around
    compute_expected_pace for backward compatibility with existing callers.
    """
    return compute_expected_pace(df)


def laps_with_delta(
    df: pd.DataFrame,
    expected_by_lap_regime: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Add pace_delta (vs race-median clean laps), lap_index_in_stint, and delta_to_stint_avg
    to lap rows. Uses reusable attach_pace_delta; preserves existing plotting interface.
    pace_delta = actual_lap_time - expected_lap_time; negative = overperformance.
    """
    valid = _valid_laps(df).copy()
    if valid.empty:
        return valid

    # Reusable: attach pace_delta from race-median (clean laps) baseline per (lap_number, tyre_regime)
    valid = attach_pace_delta(valid, expected_by_lap_regime=expected_by_lap_regime)

    # lap_index_in_stint: 1, 2, 3, ... within each (driver, stint)
    valid["lap_index_in_stint"] = valid.groupby(["driver", "stint"]).cumcount() + 1

    # stint average lap time per (driver, stint), then delta_to_stint_avg
    stint_avg = valid.groupby(["driver", "stint"])["lap_time_s"].transform("mean")
    valid["delta_to_stint_avg"] = valid["lap_time_s"].astype(float) - stint_avg

    return valid


def _linear_slope(x: pd.Series, y: pd.Series) -> float | None:
    """Linear regression slope (y vs x). Returns None if insufficient points or constant."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < MIN_LAPS_FOR_DEGRADATION:
        return None
    x, y = x[mask], y[mask]
    if np.std(x) == 0:
        return None
    coefs = np.polyfit(x, y, 1)
    return float(coefs[0])


def stint_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Group by (driver, stint, compound). For each group compute:
    laps_in_stint, avg_lap_time, fastest_lap_time, std_dev,
    degradation_slope_sec_per_lap (linear regression lap_time vs lap_index_in_stint),
    avg_pace_delta (pace delta vs race-median clean laps).
    Uses outlier-filtered laps for robustness.
    """
    valid = _valid_laps(df)
    if valid.empty:
        return pd.DataFrame(
            columns=[
                "driver",
                "team",
                "stint",
                "compound",
                "laps_in_stint",
                "avg_lap_time",
                "fastest_lap_time",
                "std_dev",
                "degradation_slope_sec_per_lap",
                "avg_pace_delta",
            ]
        )

    # Add lap_index_in_stint and pace_delta for summary
    with_delta = laps_with_delta(df)
    # Optional: use outlier-filtered data for stint stats only
    with_delta_clean = _drop_stint_outliers(with_delta)

    rows = []
    for (driver, stint, compound), grp in with_delta_clean.groupby(
        ["driver", "stint", "compound"], dropna=False
    ):
        team = grp["team"].iloc[0] if "team" in grp.columns else None
        laps_in_stint = len(grp)
        times = grp["lap_time_s"].astype(float)
        avg_lap_time = float(times.mean())
        fastest_lap_time = float(times.min())
        std_dev = float(times.std()) if laps_in_stint > 1 else None
        slope = _linear_slope(grp["lap_index_in_stint"], grp["lap_time_s"])
        avg_delta = grp["pace_delta"].mean()
        avg_pace_delta = float(avg_delta) if pd.notna(avg_delta) else None

        rows.append(
            {
                "driver": driver,
                "team": team,
                "stint": int(stint) if pd.notna(stint) else None,
                "compound": compound if pd.notna(compound) else None,
                "laps_in_stint": laps_in_stint,
                "avg_lap_time": round(avg_lap_time, 4),
                "fastest_lap_time": round(fastest_lap_time, 4),
                "std_dev": round(std_dev, 4) if std_dev is not None else None,
                "degradation_slope_sec_per_lap": round(slope, 6) if slope is not None else None,
                "avg_pace_delta": round(avg_pace_delta, 4) if avg_pace_delta is not None else None,
            }
        )

    return pd.DataFrame(rows)


def field_median_pace_by_compound(stint_summary_df: pd.DataFrame) -> dict[str, float]:
    """Median avg_lap_time per compound across all stints (for insights)."""
    if stint_summary_df.empty or "compound" not in stint_summary_df.columns:
        return {}
    medians = stint_summary_df.groupby("compound")["avg_lap_time"].median()
    return medians.astype(float).to_dict()


def compute_stint_ranges(df: pd.DataFrame) -> list[dict]:
    """
    Compute stint ranges per driver: [{driver, stint, compound, start_lap, end_lap, length_laps}].
    """
    if df.empty or "driver" not in df.columns or "stint" not in df.columns:
        return []

    ranges = []
    for (driver, stint), grp in df.groupby(["driver", "stint"], dropna=False):
        if pd.isna(stint):
            continue
        lap_nums = grp["lap_number"].dropna().astype(int)
        if lap_nums.empty:
            continue
        start_lap = int(lap_nums.min())
        end_lap = int(lap_nums.max())
        compound = grp["compound"].iloc[0] if "compound" in grp.columns else None
        team = grp["team"].iloc[0] if "team" in grp.columns else None
        ranges.append({
            "driver": driver,
            "team": team,
            "stint": int(stint),
            "compound": compound if pd.notna(compound) else None,
            "start_lap": start_lap,
            "end_lap": end_lap,
            "length_laps": end_lap - start_lap + 1,
        })
    # Sort by driver then stint
    ranges.sort(key=lambda r: (r["driver"], r["stint"]))
    return ranges


def generate_insights(
    stint_summary_df: pd.DataFrame,
    laps_with_delta_df: pd.DataFrame,
    field_median_by_compound: dict[str, float],
) -> list[str]:
    """
    Generate 3–6 deterministic insight bullets.
    """
    insights: list[str] = []
    if stint_summary_df.empty:
        insights.append("No stint data available for this race.")
        return insights[:6]

    # Best tire management: lowest degradation slope (closest to 0 or negative) among stints with >= MIN_LAPS
    long_stints = stint_summary_df[
        (stint_summary_df["laps_in_stint"] >= MIN_LAPS_FOR_INSIGHT_STINT)
        & stint_summary_df["degradation_slope_sec_per_lap"].notna()
    ]
    if not long_stints.empty:
        # Prefer least positive slope (best management)
        best = long_stints.loc[long_stints["degradation_slope_sec_per_lap"].idxmin()]
        drv = best["driver"]
        comp = best["compound"]
        slope = best["degradation_slope_sec_per_lap"]
        insights.append(
            f"Best tire management: {drv} on {comp} (degradation {slope:+.4f} s/lap over {int(best['laps_in_stint'])} laps)."
        )

    # Most consistent: lowest std_dev among stints with enough laps
    consistent = stint_summary_df[
        (stint_summary_df["laps_in_stint"] >= 3) & stint_summary_df["std_dev"].notna()
    ]
    if not consistent.empty:
        best_cons = consistent.loc[consistent["std_dev"].idxmin()]
        insights.append(
            f"Most consistent stint: {best_cons['driver']} stint {best_cons['stint']} ({best_cons['compound']}), "
            f"std dev {best_cons['std_dev']:.3f}s over {int(best_cons['laps_in_stint'])} laps."
        )

    # Biggest pace advantage: best (most negative) avg_pace_delta
    with_delta = stint_summary_df[stint_summary_df["avg_pace_delta"].notna()]
    if not with_delta.empty:
        best_pace = with_delta.loc[with_delta["avg_pace_delta"].idxmin()]
        insights.append(
            f"Biggest pace advantage: {best_pace['driver']} (avg pace delta {best_pace['avg_pace_delta']:.3f}s in stint {best_pace['stint']})."
        )

    # Compound vs field: faster than median for compound
    for _, row in stint_summary_df.iterrows():
        comp = row["compound"]
        if comp and comp in field_median_by_compound:
            med = field_median_by_compound[comp]
            if row["avg_lap_time"] < med - 0.1:
                insights.append(
                    f"{row['driver']} on {comp} averaged {row['avg_lap_time']:.2f}s (field median {med:.2f}s)."
                )
            break  # one such insight enough

    # Pit swing: compare pace_delta before vs after pit (from laps_with_delta)
    if not laps_with_delta_df.empty and "is_pit_lap" in laps_with_delta_df.columns:
        # Optional: add "Notable pit swing" by comparing pace_delta before/after pit
        pass

    # Cap at 6
    return insights[:6]


def compute_race_analyzer(df: pd.DataFrame) -> dict[str, Any]:
    """
    Run all computations and return a dict suitable for the API:
    laps_with_delta (list of dicts), stint_summary (list of dicts),
    stint_ranges (list of dicts), insights.
    """
    laps_delta = laps_with_delta(df)
    summary_df = stint_summary(df)
    field_median = field_median_pace_by_compound(summary_df)
    insights = generate_insights(summary_df, laps_delta, field_median)
    stint_ranges_list = compute_stint_ranges(df)

    # laps_with_delta: merge back so we have all original columns + new ones for each lap row.
    # Join laps_delta back to df so we have one row per lap with pace_delta, lap_index_in_stint, delta_to_stint_avg.
    # laps_delta may have fewer rows (only valid laps); API returns one record per lap with new fields (null when invalid).
    all_laps = df.copy()
    if not laps_delta.empty and not all_laps.empty:
        # Build key for merge (driver, lap_number) or use index from laps_delta
        merge_cols = [c for c in ["driver", "lap_number", "team", "lap_time_s", "compound", "stint"] if c in laps_delta.columns]
        extra = laps_delta[merge_cols + ["lap_index_in_stint", "pace_delta", "delta_to_stint_avg"]].copy()
        # Avoid duplicate columns on merge
        all_laps = all_laps.merge(
            extra[["driver", "lap_number", "lap_index_in_stint", "pace_delta", "delta_to_stint_avg"]],
            on=["driver", "lap_number"],
            how="left",
        )
    else:
        all_laps["lap_index_in_stint"] = None
        all_laps["pace_delta"] = None
        all_laps["delta_to_stint_avg"] = None

    # Ensure track_state / state_label / yellow_sectors exist (from deep_analysis); fallback GREEN if missing
    if "track_state" not in all_laps.columns:
        all_laps["track_state"] = "GREEN"
    if "state_label" not in all_laps.columns:
        all_laps["state_label"] = "GREEN"
    if "yellow_sectors" not in all_laps.columns:
        all_laps["yellow_sectors"] = [[] for _ in range(len(all_laps))]

    # Execution score (FastF1-backed deep analytics)
    exec_df = calculate_execution_score(df)
    exec_list = exec_df.replace({np.nan: None}).to_dict(orient="records") if not exec_df.empty else []
    for row in exec_list:
        for k, v in list(row.items()):
            if isinstance(v, (np.floating, np.integer)):
                row[k] = float(v) if isinstance(v, np.floating) else int(v)
            elif v is pd.NA or (isinstance(v, float) and math.isnan(v)):
                row[k] = None

    # Convert to list of dicts, NaN -> None; preserve track_state, yellow_sectors, state_label
    laps_list = all_laps.replace({np.nan: None}).to_dict(orient="records")
    for row in laps_list:
        for k, v in list(row.items()):
            if isinstance(v, (np.floating, np.integer)):
                row[k] = float(v) if isinstance(v, np.floating) else int(v)
            elif v is pd.NA or (isinstance(v, float) and math.isnan(v)):
                row[k] = None
        # Ensure yellow_sectors is JSON-serializable list of ints
        if "yellow_sectors" in row and row["yellow_sectors"] is not None:
            try:
                row["yellow_sectors"] = [int(x) for x in row["yellow_sectors"] if x is not None]
            except (TypeError, ValueError):
                row["yellow_sectors"] = []
        # raw_status: int or None
        if "raw_status" in row and row["raw_status"] is not None:
            try:
                row["raw_status"] = int(row["raw_status"])
            except (TypeError, ValueError):
                row["raw_status"] = None

    # One-time debug: count laps per track state to verify non-green states (set _TRACK_STATE_DEBUG_LOG=True)
    global _track_state_debug_logged
    if _TRACK_STATE_DEBUG_LOG and not _track_state_debug_logged and laps_list:
        from collections import Counter
        counts = Counter(row.get("track_state") or "GREEN" for row in laps_list)
        parts = " ".join(f"{k}={counts.get(k, 0)}" for k in ("GREEN", "YELLOW", "SC", "VSC", "RED"))
        _log.info("Track state lap counts: %s", parts)
        _track_state_debug_logged = True

    summary_list = summary_df.replace({np.nan: None}).to_dict(orient="records")
    for row in summary_list:
        for k, v in list(row.items()):
            if isinstance(v, (np.floating, np.integer)):
                row[k] = float(v) if isinstance(v, np.floating) else int(v)
            elif v is pd.NA or (isinstance(v, float) and math.isnan(v)):
                row[k] = None

    return {
        "laps_with_delta": laps_list,
        "stint_summary": summary_list,
        "stint_ranges": stint_ranges_list,
        "insights": insights,
        "execution_score": exec_list,
    }
