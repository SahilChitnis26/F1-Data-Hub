"""
Ergast-only, outcome-based Results Score.

Uses only reliable Ergast/Jolpica fields: position gain, finish outcome,
teammate finish delta (position-based), fastest lap, and DNF penalty.
Scaling is robust (median/MAD + winsorization) to avoid NaN explosions.
"""

from __future__ import annotations

import requests
import pandas as pd
import numpy as np
from typing import Optional

# Weights for components (config)
WEIGHT_POSITION_GAIN = 0.35
WEIGHT_FINISH_OUTCOME = 0.35
WEIGHT_TEAMMATE_DELTA = 0.20  # applied as -scaled so smaller delta is better
WEIGHT_FASTEST_LAP = 0.10
DNF_PENALTY = 2.0  # subtracted from results_score when DNF
WINSORIZE_LIMIT = 3.0

BASE_URL = "https://api.jolpi.ca/ergast/f1"


def _robust_scale(series: pd.Series, fill_missing: float = 0.0) -> pd.Series:
    """
    Scale using median and MAD: (x - median) / MAD.
    If MAD is 0, return 0 for all. Then winsorize to [-WINSORIZE_LIMIT, WINSORIZE_LIMIT].
    """
    out = pd.Series(fill_missing, index=series.index, dtype=float)
    valid = series.notna()
    if not valid.any():
        return out
    x = series.loc[valid]
    med = x.median()
    mad = (x - med).abs().median()
    if mad == 0 or np.isnan(mad):
        return out
    scaled = (x - med) / mad
    scaled = scaled.clip(lower=-WINSORIZE_LIMIT, upper=WINSORIZE_LIMIT)
    out.loc[valid] = scaled
    return out


def _get_driver_id_map(season: int, round_no: int) -> dict[str, str]:
    """Get mapping from driver full name to driverId from Ergast results."""
    url = f"{BASE_URL}/{season}/{round_no}/results.json"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return {}
    races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    if not races:
        return {}
    results = races[0].get("Results", [])
    driver_map = {}
    for r in results:
        driver_id = r.get("Driver", {}).get("driverId", "")
        given = r.get("Driver", {}).get("givenName", "")
        family = r.get("Driver", {}).get("familyName", "")
        if driver_id:
            driver_map[f"{given} {family}".strip()] = driver_id
    return driver_map


def _calculate_fastest_lap_indicator(
    df: pd.DataFrame, season: int, round_no: int
) -> pd.Series:
    """
    Return 1 if driver has fastest lap, 0 otherwise.
    Uses Ergast results API to find fastest lap driver.
    """
    out = pd.Series(0.0, index=df.index, dtype=float)
    if "driverId" not in df.columns:
        return out
    url = f"{BASE_URL}/{season}/{round_no}/results.json"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return out
    races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    if not races:
        return out
    results = races[0].get("Results", [])

    def parse_lap_time(time_str) -> Optional[float]:
        if not time_str or not isinstance(time_str, str):
            return None
        try:
            if ":" in time_str:
                parts = time_str.strip().split(":")
                return float(parts[0]) * 60 + float(parts[1])
            return float(time_str.strip())
        except (ValueError, IndexError):
            return None

    fastest_lap_time_seconds: Optional[float] = None
    fastest_lap_driver_id: Optional[str] = None
    for r in results:
        fl = r.get("FastestLap") or {}
        time_obj = fl.get("Time") or {}
        lap_time_str = time_obj.get("time", "")
        lap_time_seconds = parse_lap_time(lap_time_str)
        if lap_time_seconds is not None:
            if fastest_lap_time_seconds is None or lap_time_seconds < fastest_lap_time_seconds:
                fastest_lap_time_seconds = lap_time_seconds
                fastest_lap_driver_id = r.get("Driver", {}).get("driverId")
    if fastest_lap_driver_id is not None:
        out.loc[df["driverId"] == fastest_lap_driver_id] = 1.0
    return out


def _teammate_finish_delta_position_only(df: pd.DataFrame) -> pd.Series:
    """
    Within each constructor: finish position difference vs teammate.
    delta = my_finish - min(teammate finishes). Negative = beat teammate.
    Position-based only (no time deltas).
    """
    out = pd.Series(0.0, index=df.index, dtype=float)
    finish = pd.to_numeric(df.get("Finish", pd.Series(0, index=df.index)), errors="coerce").fillna(0)
    constructor = df.get("constructor", pd.Series("", index=df.index)).fillna("")
    for _, group in df.groupby(constructor):
        if len(group) < 2:
            out.loc[group.index] = 0.0
            continue
        idx = group.index
        my_finish = finish.loc[idx]
        # Best (min) finish among teammates
        team_best = my_finish.min()
        # delta = my_finish - team_best (0 for team best, positive if behind)
        delta = my_finish - team_best
        out.loc[idx] = delta.values
    return out


def _is_dnf(df: pd.DataFrame) -> pd.Series:
    """True if Finish missing/0 or status indicates DNF."""
    finish = pd.to_numeric(df.get("Finish", pd.Series(0, index=df.index)), errors="coerce")
    status = df.get("status", pd.Series("", index=df.index)).fillna("").astype(str).str.strip()
    missing_or_zero = finish.isna() | (finish <= 0)
    status_dnf = status.str.upper().eq("DNF")
    return missing_or_zero | status_dnf


def calculate_results_score(
    race_results_df: pd.DataFrame, season: int, round_no: int
) -> pd.DataFrame:
    """
    Compute an outcome-based Results Score using only reliable Ergast fields.

    The score measures how well a driver performed in terms of:
    - Gaining positions from grid to finish (position_gain),
    - Finish outcome (points or normalized position),
    - Beating their teammate (smaller teammate_finish_delta is better),
    - Earning fastest lap,
    with a penalty for DNFs.

    Scaling uses median and MAD (robust to outliers), then winsorization to
    [-3, 3] so the score remains stable and explainable without NaN explosions.

    Parameters
    ----------
    race_results_df : pd.DataFrame
        Race results from Ergast (e.g. fetch_race_results). Expected columns
        include: grid, Finish, points, constructor, status; driver names in
        'driver'. Missing columns are filled with 0 defaults.
    season : int
        F1 season year (e.g. 2024).
    round_no : int
        Round number (1-based).

    Returns
    -------
    pd.DataFrame
        Input frame with added columns:
        - position_gain, finish_outcome, teammate_finish_delta, fastest_lap_indicator
        - *_scaled for each component (robust-scaled and winsorized)
        - is_dnf (bool)
        - results_score (weighted sum minus DNF penalty when applicable)
    """
    df = race_results_df.copy()
    n = len(df)
    default_series = pd.Series(0, index=df.index)

    # Safe column access with 0 defaults when columns are missing
    grid = pd.to_numeric(df.get("grid", default_series), errors="coerce").fillna(0).astype(int)
    finish = pd.to_numeric(df.get("Finish", default_series), errors="coerce").fillna(0).astype(int)
    points = pd.to_numeric(df.get("points", default_series), errors="coerce").fillna(0)

    # --- position_gain = grid - finish (higher is better) ---
    df["position_gain"] = grid - finish

    # --- finish_outcome: points if present, else normalized position (P1 best) ---
    # Normalized: (n - finish + 1) so P1 = n, last = 1; use 0 for invalid finish
    max_pos = max(1, int(finish.max()) if finish.max() > 0 else 1)
    normalized_pos = np.where(finish >= 1, max_pos - finish + 1, 0)
    df["finish_outcome"] = np.where(points > 0, points, normalized_pos)

    # --- teammate_finish_delta (position-based only) ---
    df["teammate_finish_delta"] = _teammate_finish_delta_position_only(df)

    # --- driverId for fastest lap (Ergast) ---
    driver_id_map = _get_driver_id_map(season, round_no)
    df["driverId"] = df.get("driver", pd.Series("", index=df.index)).map(driver_id_map)

    # --- fastest_lap_indicator ---
    df["fastest_lap_indicator"] = _calculate_fastest_lap_indicator(df, season, round_no)

    # --- DNF flag ---
    df["is_dnf"] = _is_dnf(df)

    # --- Robust scaling + winsorize ---
    df["position_gain_scaled"] = _robust_scale(df["position_gain"])
    df["finish_outcome_scaled"] = _robust_scale(df["finish_outcome"])
    df["teammate_finish_delta_scaled"] = _robust_scale(df["teammate_finish_delta"])
    # fastest_lap_indicator is already 0/1, no scaling

    # --- Weighted results_score ---
    # Smaller teammate_finish_delta is better -> use -teammate_finish_delta_scaled
    df["results_score"] = (
        WEIGHT_POSITION_GAIN * df["position_gain_scaled"].fillna(0)
        + WEIGHT_FINISH_OUTCOME * df["finish_outcome_scaled"].fillna(0)
        + WEIGHT_TEAMMATE_DELTA * (-df["teammate_finish_delta_scaled"].fillna(0))
        + WEIGHT_FASTEST_LAP * df["fastest_lap_indicator"].fillna(0)
    )

    # --- DNF penalty at the end ---
    df.loc[df["is_dnf"], "results_score"] = (
        df.loc[df["is_dnf"], "results_score"] - DNF_PENALTY
    )

    df["results_score"] = df["results_score"].round(3)
    return df
