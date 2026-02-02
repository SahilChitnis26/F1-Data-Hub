"""
FastF1-backed Execution Score: deep analytics from lap-level pace data.

Uses the DataFrame returned by fetch_lap_pace() to compute per-driver metrics:
pace (median delta to leader), consistency (MAD of delta), degradation slope,
and pit loss proxy. Combines with robust scaling into a single execution_score.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

WINSORIZE_LIMIT = 3.0
WEIGHT_PACE = 0.45
WEIGHT_DEG = 0.20
WEIGHT_CONSISTENCY = 0.15
WEIGHT_PIT_LOSS = 0.20
MIN_LAPS_FOR_DEGRADATION = 6
MIN_CLEAN_LAPS_BASELINE = 3


def _clean_laps_mask(df: pd.DataFrame) -> pd.Series:
    """Boolean mask: exclude pit out, in, pit laps and missing/<=0 lap_time_s."""
    if df.empty or "lap_time_s" not in df.columns:
        return pd.Series(False, index=df.index)
    lap_ok = df["lap_time_s"].notna() & (df["lap_time_s"] > 0)
    pit_out = df["is_pit_out_lap"].fillna(False)
    in_lap = df["is_in_lap"].fillna(False)
    pit_lap = df["is_pit_lap"].fillna(False)
    return lap_ok & ~pit_out & ~in_lap & ~pit_lap


def _robust_scale(series: pd.Series, fill_missing: float = 0.0) -> pd.Series:
    """Scale (x - median) / MAD, winsorize to [-3, 3]. Missing -> fill_missing."""
    out = pd.Series(fill_missing, index=series.index, dtype=float)
    valid = series.notna()
    if not valid.any():
        return out
    x = series.loc[valid]
    med = x.median()
    mad = (x - med).abs().median()
    if mad == 0 or (mad != mad):
        return out
    scaled = (x - med) / mad
    scaled = scaled.clip(lower=-WINSORIZE_LIMIT, upper=WINSORIZE_LIMIT)
    out.loc[valid] = scaled
    return out


def _linear_slope(x: pd.Series, y: pd.Series) -> float | None:
    """Linear regression slope (y vs x). Returns None if insufficient points."""
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    mask = np.isfinite(x_arr) & np.isfinite(y_arr)
    if mask.sum() < MIN_LAPS_FOR_DEGRADATION:
        return None
    x_arr, y_arr = x_arr[mask], y_arr[mask]
    if np.std(x_arr) == 0:
        return None
    coefs = np.polyfit(x_arr, y_arr, 1)
    return float(coefs[0])


def _compute_delta_to_leader(df: pd.DataFrame, clean_mask: pd.Series) -> pd.Series:
    """Compute delta_to_leader per row: lap_time_s - min(lap_time_s) for that lap_number among clean laps."""
    df = df.copy()
    df["_clean"] = clean_mask
    # Leader time per lap_number: min among clean laps only
    leader_map = df.loc[df["_clean"]].groupby("lap_number")["lap_time_s"].min()
    df["_leader"] = df["lap_number"].map(leader_map)
    delta = df["lap_time_s"].astype(float) - df["_leader"]
    return delta


def _compute_pit_loss_proxy(
    df: pd.DataFrame, delta_to_leader: pd.Series, clean_mask: pd.Series
) -> pd.Series:
    """
    For each pit event: baseline = median(delta) of 3 clean laps before pit,
    window = max(delta) in [pit lap, out lap]. pit_loss += max(0, window - baseline).
    Returns per-driver total pit_loss_proxy.
    """
    work = df.copy()
    work["delta"] = delta_to_leader
    work["_clean"] = clean_mask
    work = work.sort_values(["driver", "lap_number"]).reset_index(drop=True)

    pit_loss_by_driver: dict[str, float] = {}
    for driver, grp in work.groupby("driver", sort=False):
        grp = grp.sort_values("lap_number").reset_index(drop=True)
        total_loss = 0.0

        # Find pit events: is_in_lap == True
        in_lap_rows = grp[grp["is_in_lap"].fillna(False)]
        for _, in_row in in_lap_rows.iterrows():
            in_lap_num = in_row["lap_number"]
            # Out lap: next lap (is_pit_out_lap)
            out_rows = grp[(grp["lap_number"] > in_lap_num) & (grp["is_pit_out_lap"].fillna(False))]
            out_lap_num = out_rows["lap_number"].min() if not out_rows.empty else None

            # Baseline: median delta of 3 clean laps before pit
            before = grp[(grp["lap_number"] < in_lap_num) & grp["_clean"]].tail(3)
            if len(before) < 1:
                baseline = 0.0
            else:
                baseline = float(before["delta"].median())

            # Window: max(delta) in [pit lap, out lap]
            window_laps = grp[
                (grp["lap_number"] >= in_lap_num)
                & (
                    (grp["lap_number"] == in_lap_num)
                    | ((out_lap_num is not None) & (grp["lap_number"] == out_lap_num))
                )
            ]
            if window_laps.empty:
                continue
            window_deltas = window_laps["delta"].dropna()
            if window_deltas.empty:
                continue
            window_max = float(window_deltas.max())
            total_loss += max(0.0, window_max - baseline)

        pit_loss_by_driver[driver] = total_loss

    return pd.Series(pit_loss_by_driver)


def calculate_execution_score(laps_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute per-driver Execution Score from lap-level pace data (e.g. fetch_lap_pace output).

    Metrics:
    - pace_med_delta: median(delta_to_leader) on clean laps (lower is better)
    - consistency_mad: MAD(delta_to_leader) on clean laps (lower is better)
    - deg_slope: median regression slope of lap_time vs lap_index_in_stint per stint (lower is better)
    - pit_loss_proxy: sum over pit events of max(0, window_max - baseline) (lower is better)

    Scaling: robust (median/MAD + winsorize [-3,3]). Weights:
    0.45 * (-pace_scaled) + 0.20 * (-deg_scaled) + 0.15 * (-consistency_scaled) + 0.20 * (-pitloss_scaled)

    Drivers with too few clean laps get neutral (0) for missing components.
    Output has no NaNs in execution_score.

    Parameters
    ----------
    laps_df : pd.DataFrame
        Lap-level data from fetch_lap_pace(). Expected columns: driver, lap_number,
        lap_time_s, stint, is_pit_out_lap, is_in_lap, is_pit_lap.

    Returns
    -------
    pd.DataFrame
        One row per driver with: driver, execution_score, pace_med_delta,
        consistency_mad, deg_slope, pit_loss_proxy, pace_scaled, consistency_scaled,
        deg_scaled, pitloss_scaled.
    """
    if laps_df.empty or "driver" not in laps_df.columns:
        return pd.DataFrame(
            columns=[
                "driver",
                "execution_score",
                "pace_med_delta",
                "consistency_mad",
                "deg_slope",
                "pit_loss_proxy",
                "pace_scaled",
                "consistency_scaled",
                "deg_scaled",
                "pitloss_scaled",
            ]
        )

    df = laps_df.copy()
    clean_mask = _clean_laps_mask(df)

    # Ensure stint exists
    if "stint" not in df.columns:
        df["stint"] = 1

    # Delta to leader (using clean laps only for leader definition)
    delta_to_leader = _compute_delta_to_leader(df, clean_mask)
    df["delta_to_leader"] = delta_to_leader

    # lap_index_in_stint for degradation
    df["lap_index_in_stint"] = (
        df.groupby(["driver", "stint"], dropna=False).cumcount() + 1
    )

    drivers = df["driver"].unique()

    # --- pace_med_delta ---
    pace_med = (
        df.loc[clean_mask]
        .groupby("driver")["delta_to_leader"]
        .median()
        .reindex(drivers)
    )

    # --- consistency_mad ---
    def _mad(grp):
        d = grp["delta_to_leader"]
        if len(d) < 2:
            return np.nan
        med = d.median()
        return (d - med).abs().median()

    consistency_mad = (
        df.loc[clean_mask]
        .groupby("driver")
        .apply(_mad, include_groups=False)
        .reindex(drivers)
    )

    # --- deg_slope: median slope per driver over stints with >=6 clean laps ---
    slopes = []
    for (driver, stint), grp in df.groupby(["driver", "stint"], dropna=False):
        clean_grp = grp[clean_mask.loc[grp.index]]
        if len(clean_grp) >= MIN_LAPS_FOR_DEGRADATION:
            slope = _linear_slope(
                clean_grp["lap_index_in_stint"],
                clean_grp["lap_time_s"],
            )
            if slope is not None:
                slopes.append({"driver": driver, "slope": slope})
    if slopes:
        slope_df = pd.DataFrame(slopes)
        deg_slope = slope_df.groupby("driver")["slope"].median().reindex(drivers)
    else:
        deg_slope = pd.Series(index=drivers, dtype=float)

    # --- pit_loss_proxy ---
    pit_loss = _compute_pit_loss_proxy(df, delta_to_leader, clean_mask)
    pit_loss = pit_loss.reindex(drivers).fillna(0.0)

    # Build per-driver table
    result = pd.DataFrame(index=drivers)
    result.index.name = "driver"
    result = result.reset_index()
    result["pace_med_delta"] = pace_med.values
    result["consistency_mad"] = consistency_mad.values
    result["deg_slope"] = deg_slope.values
    result["pit_loss_proxy"] = pit_loss.values

    # Robust scaling (neutral 0 for missing)
    result["pace_scaled"] = _robust_scale(result["pace_med_delta"])
    result["consistency_scaled"] = _robust_scale(result["consistency_mad"])
    result["deg_scaled"] = _robust_scale(result["deg_slope"])
    result["pitloss_scaled"] = _robust_scale(result["pit_loss_proxy"])

    # Fill NaNs in scaled columns with 0 (neutral)
    for col in ["pace_scaled", "consistency_scaled", "deg_scaled", "pitloss_scaled"]:
        result[col] = result[col].fillna(0.0)

    result["execution_score"] = (
        WEIGHT_PACE * (-result["pace_scaled"])
        + WEIGHT_DEG * (-result["deg_scaled"])
        + WEIGHT_CONSISTENCY * (-result["consistency_scaled"])
        + WEIGHT_PIT_LOSS * (-result["pitloss_scaled"])
    )
    result["execution_score"] = result["execution_score"].round(3)
    result["execution_score"] = result["execution_score"].fillna(0.0)  # ensure no NaNs

    return result
