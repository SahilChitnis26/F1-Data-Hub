"""
FastF1-backed Execution Score: deep analytics from lap-level pace data.

Uses the DataFrame returned by fetch_lap_pace() to compute per-driver metrics:
pace (median pace delta vs race-median clean laps), consistency (MAD of pace delta),
degradation slope, and pit loss proxy. Combines with robust scaling into a single execution_score.
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

# Clean lap: lap_number >= 2, not pit, track green, lap time non-null and within bounds.
# Only clean laps are used to compute expected pace.
LAP_NUMBER_MIN_CLEAN = 2
LAP_TIME_BOUND_PERCENTILE_LOW = 1.0
LAP_TIME_BOUND_PERCENTILE_HIGH = 99.0


def _clean_laps_mask(df: pd.DataFrame) -> pd.Series:
    """
    Boolean mask for "clean" laps. A clean lap meets ALL of:
    - Lap number >= 2 (exclude Lap 1 entirely)
    - Not a pit-in or pit-out lap
    - Track status is green (exclude SC / VSC / red flag laps)
    - Lap time is non-null and within reasonable bounds (drop extreme outliers)
    Clean laps are the ONLY laps used to compute expected pace.
    """
    if df.empty or "lap_time_s" not in df.columns:
        return pd.Series(False, index=df.index)
    lap_num_ok = df["lap_number"].ge(LAP_NUMBER_MIN_CLEAN)
    lap_ok = df["lap_time_s"].notna() & (df["lap_time_s"] > 0)
    pit_out = df["is_pit_out_lap"].fillna(False)
    in_lap = df["is_in_lap"].fillna(False)
    pit_lap = df["is_pit_lap"].fillna(False)
    not_pit = ~pit_out & ~in_lap & ~pit_lap
    track_green = (
        df["is_track_green"].fillna(True)
        if "is_track_green" in df.columns
        else pd.Series(True, index=df.index)
    )
    candidate = lap_num_ok & lap_ok & not_pit & track_green
    if not candidate.any():
        return candidate
    # Drop extreme lap-time outliers: keep within percentile bounds of candidate laps
    times = df.loc[candidate, "lap_time_s"].astype(float)
    low = np.nanpercentile(times, LAP_TIME_BOUND_PERCENTILE_LOW)
    high = np.nanpercentile(times, LAP_TIME_BOUND_PERCENTILE_HIGH)
    in_bounds = (df["lap_time_s"].astype(float) >= low) & (
        df["lap_time_s"].astype(float) <= high
    )
    return candidate & in_bounds


# Public alias for use by race_analyzer and others
clean_laps_mask = _clean_laps_mask


def build_clean_laps(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a DataFrame containing only "clean" laps derived from FastF1 session.laps.

    Clean laps are used to compute the expected-pace baseline. They exclude Lap 1,
    pit-in/pit-out laps, non-green track (SC/VSC/red), and extreme lap-time outliers.
    This keeps the baseline stable so pit stops and safety car periods appear as
    visible spikes or gaps in pace_delta, not as baseline shifts.

    Parameters
    ----------
    df : pd.DataFrame
        Lap-level data from fetch_lap_pace() (FastF1 session.laps). Expected columns:
        lap_number, lap_time_s, is_pit_out_lap, is_in_lap, is_pit_lap, optionally
        is_track_green.

    Returns
    -------
    pd.DataFrame
        Subset of df where clean_laps_mask is True. Same columns as input.
    """
    if df.empty:
        return df.copy()
    mask = _clean_laps_mask(df)
    return df.loc[mask].copy()


def compute_expected_pace(
    df: pd.DataFrame, clean_mask: pd.Series | None = None
) -> pd.DataFrame:
    """
    Compute expected lap time per (lap_number, tyre_regime) from clean laps only.

    Expected pace = rolling median of clean laps in window [lap_number - k, lap_number + k]
    (k=2 first, then k=4 if insufficient samples). Slick and wet runners use separate
    baselines (tyre_regime SLICK vs WET); regimes are never mixed. In a dry race,
    expected pace can gradually improve over race distance (fuel burn, tire evolution).
    Lap 1 is excluded from computation and never receives an expected pace.

    Parameters
    ----------
    df : pd.DataFrame
        Lap-level data from fetch_lap_pace(). Must have lap_number, lap_time_s,
        compound (or tyre_regime).
    clean_mask : pd.Series, optional
        Boolean mask of clean laps. If None, computed via clean_laps_mask(df).

    Returns
    -------
    pd.DataFrame
        Columns: lap_number, tyre_regime, expected_lap_time_s. One row per
        (lap_number, tyre_regime) with lap_number >= 2.
    """
    if clean_mask is None:
        clean_mask = _clean_laps_mask(df)
    return expected_pace_rolling(df, clean_mask)


def attach_pace_delta(
    df: pd.DataFrame,
    expected_by_lap_regime: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Attach pace_delta to each lap row in place (modifies a copy and returns it).

    pace_delta = actual_lap_time_s - expected_lap_time_s, where expected_lap_time_s
    comes from the race-median baseline (clean laps, per lap_number and tyre_regime).
    Negative = overperformance, positive = underperformance. Lap 1 never receives
    a pace_delta (no baseline). Pit stops and safety car laps get pace_delta vs
    the same baseline, so they appear as spikes/gaps, not baseline shifts.

    Parameters
    ----------
    df : pd.DataFrame
        Lap-level data with lap_number, lap_time_s, compound (or tyre_regime).
    expected_by_lap_regime : pd.DataFrame, optional
        Output of compute_expected_pace(df). If None, computed from df.

    Returns
    -------
    pd.DataFrame
        df with added column pace_delta (float; NaN for lap 1 or when no expected pace).
    """
    out = df.copy()
    if "tyre_regime" not in out.columns:
        out["tyre_regime"] = _tyre_regime_from_compound(out)
    if expected_by_lap_regime is None or expected_by_lap_regime.empty:
        expected_by_lap_regime = compute_expected_pace(out)
    if expected_by_lap_regime.empty:
        out["pace_delta"] = np.nan
        return out
    out = out.merge(
        expected_by_lap_regime,
        on=["lap_number", "tyre_regime"],
        how="left",
    )
    pace_delta = out["lap_time_s"].astype(float) - out["expected_lap_time_s"].astype(float)
    # Lap 1 must not receive a pace delta under any circumstances
    lap1_mask = out["lap_number"] == 1
    out["pace_delta"] = pace_delta.where(~lap1_mask, np.nan)
    out.drop(columns=["expected_lap_time_s"], inplace=True, errors="ignore")
    return out


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


# Rolling expected pace: window [l-k, l+k], k=2 (5-lap); min 8 clean laps; else k=4; else NaN.
# Lap 1 is never used in expected pace computation and never receives a pace delta.
# Validation: In a dry race, expected pace can gradually improve over race distance (fuel/tire).
# Mixed conditions: slick and wet have separate baselines (tyre_regime); never mixed.
# Pit/SC: excluded from clean_laps, so they do not shift the baseline; they appear as spikes/gaps.
ROLLING_K = 2
ROLLING_K_WIDE = 4
MIN_CLEAN_LAPS_IN_WINDOW = 8


def _tyre_regime_from_compound(df: pd.DataFrame) -> pd.Series:
    """Derive tyre_regime (SLICK vs WET) from compound if not present. SLICK=Soft/Medium/Hard, WET=Intermediate/Wet."""
    if "tyre_regime" in df.columns:
        return df["tyre_regime"]
    if "compound" not in df.columns:
        return pd.Series("SLICK", index=df.index)
    comp = df["compound"].astype(str).str.upper()
    return np.where(comp.isin(["INTERMEDIATE", "WET"]), "WET", "SLICK")


def expected_pace_rolling(
    df: pd.DataFrame, clean_mask: pd.Series
) -> pd.DataFrame:
    """
    For each (lap_number, tyre_regime), expected_pace = rolling median of clean laps
    in window [l-k, l+k]. k=2 first; if fewer than 8 clean laps, try k=4; else NaN.
    Lap 1 is fully excluded from expected pace computation (never in output).
    """
    work = df.copy()
    work["_clean"] = clean_mask
    if "tyre_regime" not in work.columns:
        work["tyre_regime"] = _tyre_regime_from_compound(work)
    clean_laps = work.loc[work["_clean"]].copy()
    if clean_laps.empty:
        return pd.DataFrame(columns=["lap_number", "tyre_regime", "expected_lap_time_s"])

    # Lap 1 must never influence baseline: only laps with lap_number >= 2 are in clean_laps (LAP_NUMBER_MIN_CLEAN=2)
    # Compute expected pace only for (lap_number, tyre_regime) pairs that appear in the data (lap_number >= 2)
    keys = (
        work.loc[work["lap_number"] >= 2, ["lap_number", "tyre_regime"]]
        .drop_duplicates()
        .sort_values(["lap_number", "tyre_regime"])
    )
    if keys.empty:
        return pd.DataFrame(columns=["lap_number", "tyre_regime", "expected_lap_time_s"])
    rows = []
    for _, row in keys.iterrows():
        lap_num = int(row["lap_number"])
        regime = row["tyre_regime"]
        # Window [lap_num - k, lap_num + k]; try k=2 first (5-lap window)
        window_laps = clean_laps[
            (clean_laps["tyre_regime"] == regime)
            & (clean_laps["lap_number"] >= lap_num - ROLLING_K)
            & (clean_laps["lap_number"] <= lap_num + ROLLING_K)
        ]
        n = len(window_laps)
        if n >= MIN_CLEAN_LAPS_IN_WINDOW:
            expected_s = float(window_laps["lap_time_s"].median())
            rows.append({"lap_number": lap_num, "tyre_regime": regime, "expected_lap_time_s": expected_s})
            continue
        # Widen to k=4
        window_laps = clean_laps[
            (clean_laps["tyre_regime"] == regime)
            & (clean_laps["lap_number"] >= lap_num - ROLLING_K_WIDE)
            & (clean_laps["lap_number"] <= lap_num + ROLLING_K_WIDE)
        ]
        n = len(window_laps)
        if n >= MIN_CLEAN_LAPS_IN_WINDOW:
            expected_s = float(window_laps["lap_time_s"].median())
            rows.append({"lap_number": lap_num, "tyre_regime": regime, "expected_lap_time_s": expected_s})
        else:
            rows.append({"lap_number": lap_num, "tyre_regime": regime, "expected_lap_time_s": np.nan})
    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=["lap_number", "tyre_regime", "expected_lap_time_s"])
    return out


def _compute_pace_delta(df: pd.DataFrame, clean_mask: pd.Series) -> pd.Series:
    """
    Compute pace_delta per row using attach_pace_delta (race-median clean-laps baseline).
    Returns a Series aligned to df.index for use inside calculate_execution_score.
    """
    with_delta = attach_pace_delta(df, expected_by_lap_regime=expected_pace_rolling(df, clean_mask))
    return with_delta["pace_delta"]


def _compute_pit_loss_proxy(
    df: pd.DataFrame, pace_delta: pd.Series, clean_mask: pd.Series
) -> pd.Series:
    """
    For each pit event: baseline = median(pace_delta) of 3 clean laps before pit,
    window = max(pace_delta) in [pit lap, out lap]. pit_loss += max(0, window - baseline).
    Returns per-driver total pit_loss_proxy.
    """
    work = df.copy()
    work["delta"] = pace_delta
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
    - pace_med_delta: median(pace_delta) on clean laps, pace_delta = actual - race-median expected (lower is better)
    - consistency_mad: MAD(pace_delta) on clean laps (lower is better)
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
        lap_time_s, compound (or tyre_regime), stint, is_pit_out_lap, is_in_lap, is_pit_lap.
        Optional: is_track_green (bool; default True if missing). Clean laps (lap >= 2,
        not pit, track green, lap time in bounds) are the only laps used for expected pace.

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

    # Pace delta vs race-median (clean laps), by lap_number and tyre_regime
    pace_delta = _compute_pace_delta(df, clean_mask)
    df["pace_delta"] = pace_delta

    # lap_index_in_stint for degradation
    df["lap_index_in_stint"] = (
        df.groupby(["driver", "stint"], dropna=False).cumcount() + 1
    )

    drivers = df["driver"].unique()

    # --- pace_med_delta ---
    pace_med = (
        df.loc[clean_mask]
        .groupby("driver")["pace_delta"]
        .median()
        .reindex(drivers)
    )

    # --- consistency_mad ---
    def _mad(grp):
        d = grp["pace_delta"]
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
    pit_loss = _compute_pit_loss_proxy(df, pace_delta, clean_mask)
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
