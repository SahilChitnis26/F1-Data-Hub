"""
Race analyzer: leader-by-lap, deltas, stint summary, execution score, and deterministic insights.
Uses only valid lap times; optional outlier removal per stint.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from ..scoring.execution_score import calculate_execution_score

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


def leader_by_lap(df: pd.DataFrame) -> dict[int, float]:
    """
    For each lap number, the leader's lap time (min lap_time_s across drivers).
    Only considers valid lap times.
    """
    valid = _valid_laps(df)
    if valid.empty or "lap_number" not in valid.columns:
        return {}
    agg = valid.groupby("lap_number")["lap_time_s"].min()
    return agg.astype(float).to_dict()


def laps_with_delta(
    df: pd.DataFrame,
    leader_by_lap_map: dict[int, float] | None = None,
) -> pd.DataFrame:
    """
    Add delta_to_leader, lap_index_in_stint, and delta_to_stint_avg to lap rows.
    """
    valid = _valid_laps(df).copy()
    if valid.empty:
        return valid

    if leader_by_lap_map is None:
        leader_by_lap_map = leader_by_lap(df)

    # lap_index_in_stint: 1, 2, 3, ... within each (driver, stint)
    valid["lap_index_in_stint"] = valid.groupby(["driver", "stint"]).cumcount() + 1

    # delta_to_leader
    valid["lap_number_int"] = valid["lap_number"].astype(int)
    valid["leader_lap_time_s"] = valid["lap_number_int"].map(leader_by_lap_map)
    valid["delta_to_leader"] = np.where(
        valid["leader_lap_time_s"].notna(),
        valid["lap_time_s"].astype(float) - valid["leader_lap_time_s"],
        None,
    )
    valid.drop(columns=["lap_number_int", "leader_lap_time_s"], inplace=True)

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
    avg_delta_to_leader.
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
                "avg_delta_to_leader",
            ]
        )

    # Add lap_index_in_stint and delta_to_leader for summary
    leader_map = leader_by_lap(df)
    with_delta = laps_with_delta(df, leader_by_lap_map=leader_map)
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
        avg_delta = grp["delta_to_leader"].mean()
        avg_delta_to_leader = float(avg_delta) if pd.notna(avg_delta) else None

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
                "avg_delta_to_leader": round(avg_delta_to_leader, 4) if avg_delta_to_leader is not None else None,
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

    # Biggest pace advantage: best (most negative) avg_delta_to_leader
    with_delta = stint_summary_df[stint_summary_df["avg_delta_to_leader"].notna()]
    if not with_delta.empty:
        best_pace = with_delta.loc[with_delta["avg_delta_to_leader"].idxmin()]
        insights.append(
            f"Biggest pace advantage: {best_pace['driver']} (avg delta to leader {best_pace['avg_delta_to_leader']:.3f}s in stint {best_pace['stint']})."
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

    # Pit swing: compare delta before vs after pit (from laps_with_delta)
    if not laps_with_delta_df.empty and "is_pit_lap" in laps_with_delta_df.columns:
        # Simple check: driver with biggest delta improvement after a pit (next lap vs lap before pit)
        # We could iterate drivers and find pit laps, then compare delta_to_leader before/after
        pass  # Optional: add "Notable pit swing" if we have pit_lap flags and delta

    # Cap at 6
    return insights[:6]


def compute_race_analyzer(df: pd.DataFrame) -> dict[str, Any]:
    """
    Run all computations and return a dict suitable for the API:
    leader_by_lap, laps_with_delta (list of dicts), stint_summary (list of dicts),
    stint_ranges (list of dicts), insights.
    """
    leader_map = leader_by_lap(df)
    laps_delta = laps_with_delta(df, leader_by_lap_map=leader_map)
    summary_df = stint_summary(df)
    field_median = field_median_pace_by_compound(summary_df)
    insights = generate_insights(summary_df, laps_delta, field_median)
    stint_ranges_list = compute_stint_ranges(df)

    # laps_with_delta: merge back so we have all original columns + new ones for each lap row
    # We need to join laps_delta back to df so we have one row per lap with delta_to_leader, lap_index_in_stint, delta_to_stint_avg
    # laps_delta might have fewer rows (only valid laps). For API we want one record per lap with the new fields (null when invalid).
    all_laps = df.copy()
    if not laps_delta.empty and not all_laps.empty:
        # Build key for merge (driver, lap_number) or use index from laps_delta
        merge_cols = [c for c in ["driver", "lap_number", "team", "lap_time_s", "compound", "stint"] if c in laps_delta.columns]
        extra = laps_delta[merge_cols + ["lap_index_in_stint", "delta_to_leader", "delta_to_stint_avg"]].copy()
        # Avoid duplicate columns on merge
        all_laps = all_laps.merge(
            extra[["driver", "lap_number", "lap_index_in_stint", "delta_to_leader", "delta_to_stint_avg"]],
            on=["driver", "lap_number"],
            how="left",
        )
    else:
        all_laps["lap_index_in_stint"] = None
        all_laps["delta_to_leader"] = None
        all_laps["delta_to_stint_avg"] = None

    # Execution score (FastF1-backed deep analytics)
    exec_df = calculate_execution_score(df)
    exec_list = exec_df.replace({np.nan: None}).to_dict(orient="records") if not exec_df.empty else []
    for row in exec_list:
        for k, v in list(row.items()):
            if isinstance(v, (np.floating, np.integer)):
                row[k] = float(v) if isinstance(v, np.floating) else int(v)
            elif v is pd.NA or (isinstance(v, float) and math.isnan(v)):
                row[k] = None

    # Convert to list of dicts, NaN -> None
    laps_list = all_laps.replace({np.nan: None}).to_dict(orient="records")
    for row in laps_list:
        for k, v in list(row.items()):
            if isinstance(v, (np.floating, np.integer)):
                row[k] = float(v) if isinstance(v, np.floating) else int(v)
            elif v is pd.NA or (isinstance(v, float) and math.isnan(v)):
                row[k] = None

    summary_list = summary_df.replace({np.nan: None}).to_dict(orient="records")
    for row in summary_list:
        for k, v in list(row.items()):
            if isinstance(v, (np.floating, np.integer)):
                row[k] = float(v) if isinstance(v, np.floating) else int(v)
            elif v is pd.NA or (isinstance(v, float) and math.isnan(v)):
                row[k] = None

    return {
        "leader_by_lap": {int(k): float(v) for k, v in leader_map.items()},
        "laps_with_delta": laps_list,
        "stint_summary": summary_list,
        "stint_ranges": stint_ranges_list,
        "insights": insights,
        "execution_score": exec_list,
    }
