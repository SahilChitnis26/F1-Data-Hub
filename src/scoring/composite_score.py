import requests
import pandas as pd
import numpy as np
from typing import Optional

BASE_URL = "https://api.jolpi.ca/ergast/f1"


def fetch_lap_times(season: int, round_no: int) -> pd.DataFrame:
    """
    Fetch lap times for all drivers in a race.
    Returns a DataFrame with columns: driverId, lap, time_ms
    """
    url = f"{BASE_URL}/{season}/{round_no}/laps.json?limit=1000"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    
    races = data["MRData"]["RaceTable"]["Races"]
    if not races:
        return pd.DataFrame(columns=["driverId", "lap", "time_ms"])
    
    race = races[0]
    laps_data = race.get("Laps", [])
    
    rows = []
    for lap_info in laps_data:
        lap_number = int(lap_info["number"])
        timings = lap_info.get("Timings", [])
        
        for timing in timings:
            driver_id = timing["driverId"]
            time_str = timing.get("time", "")
            
            # Convert time string (e.g., "1:23.456") to milliseconds
            if time_str:
                time_ms = _time_string_to_ms(time_str)
                rows.append({
                    "driverId": driver_id,
                    "lap": lap_number,
                    "time_ms": time_ms
                })
    
    return pd.DataFrame(rows)


def fetch_pit_stops(season: int, round_no: int) -> pd.DataFrame:
    """
    Fetch pit stop data for all drivers in a race.
    Returns a DataFrame with columns: driverId, stop, duration_ms
    """
    url = f"{BASE_URL}/{season}/{round_no}/pitstops.json"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    
    races = data["MRData"]["RaceTable"]["Races"]
    if not races:
        return pd.DataFrame(columns=["driverId", "stop", "duration_ms"])
    
    race = races[0]
    pit_stops = race.get("PitStops", [])
    
    rows = []
    for pit_stop in pit_stops:
        driver_id = pit_stop["driverId"]
        duration_str = pit_stop.get("duration", "")
        
        # Convert duration string to milliseconds
        # Formats: "23.456" (seconds) or "39:18.026" (minutes:seconds.milliseconds)
        if duration_str:
            try:
                if ":" in duration_str:
                    # Format: "MM:SS.mmm"
                    parts = duration_str.split(":")
                    minutes = float(parts[0])
                    seconds_part = parts[1]
                    seconds = float(seconds_part)
                    duration_ms = (minutes * 60 + seconds) * 1000
                else:
                    # Format: "SS.mmm" (seconds)
                    duration_ms = float(duration_str) * 1000
            except (ValueError, IndexError):
                duration_ms = np.nan
            
            rows.append({
                "driverId": driver_id,
                "stop": int(pit_stop["stop"]),
                "duration_ms": duration_ms
            })
    
    return pd.DataFrame(rows)


def _time_string_to_ms(time_str: str) -> float:
    """
    Convert time string to milliseconds.
    Formats: "1:23.456" or "23.456"
    """
    try:
        if ":" in time_str:
            parts = time_str.split(":")
            minutes = float(parts[0])
            seconds = float(parts[1])
            return (minutes * 60 + seconds) * 1000
        else:
            return float(time_str) * 1000
    except (ValueError, IndexError):
        return np.nan


def calculate_composite_score(
    race_results_df: pd.DataFrame,
    season: int,
    round_no: int
) -> pd.DataFrame:
    """
    Calculate weighted composite performance score for each driver.
    
    Performance Score = 
        0.28 * z(position_gain)
      + 0.23 * -z(lap_time_mean)
      + 0.18 * -z(lap_time_std)
      + 0.13 * -z(pit_time)
      + 0.08 * -z(teammate_delta)
      + 0.10 * fastest_lap_indicator
    
    Returns DataFrame with added 'performance_score' column.
    """
    df = race_results_df.copy()
    
    # Get driver IDs from race results
    # We need to map driver names back to driverIds
    driver_id_map = _get_driver_id_map(season, round_no)
    df["driverId"] = df["driver"].map(driver_id_map)
    
    # Calculate position gain (grid - finish, higher is better)
    # Handle Finish column which might be a string (centered) or int
    finish_positions = pd.to_numeric(df["Finish"], errors='coerce').fillna(0).astype(int)
    df["position_gain"] = df["grid"] - finish_positions
    
    # Fetch lap times and calculate statistics
    lap_times_df = fetch_lap_times(season, round_no)
    if not lap_times_df.empty:
        lap_stats = lap_times_df.groupby("driverId").agg({
            "time_ms": ["mean", "std"]
        }).reset_index()
        lap_stats.columns = ["driverId", "lap_time_mean", "lap_time_std"]
        df = df.merge(lap_stats, on="driverId", how="left")
    else:
        df["lap_time_mean"] = np.nan
        df["lap_time_std"] = np.nan
    
    # Fetch pit stops and calculate total pit time
    pit_stops_df = fetch_pit_stops(season, round_no)
    if not pit_stops_df.empty:
        pit_stats = pit_stops_df.groupby("driverId")["duration_ms"].sum().reset_index()
        pit_stats.columns = ["driverId", "pit_time"]
        df = df.merge(pit_stats, on="driverId", how="left")
    else:
        df["pit_time"] = np.nan
    
    # Calculate teammate delta (time difference from teammate)
    df["teammate_delta"] = _calculate_teammate_delta(df)
    
    # Calculate fastest lap indicator (1 if driver has fastest lap, 0 otherwise)
    df["fastest_lap_indicator"] = _calculate_fastest_lap_indicator(df, season, round_no)
    
    # Z-score normalization for each metric
    metrics = ["position_gain", "lap_time_mean", "lap_time_std", "pit_time", "teammate_delta"]
    
    for metric in metrics:
        if metric in df.columns:
            # Only normalize non-null values
            valid_mask = df[metric].notna()
            if valid_mask.sum() > 1:  # Need at least 2 values for std
                mean_val = df.loc[valid_mask, metric].mean()
                std_val = df.loc[valid_mask, metric].std()
                if std_val > 0:
                    df[f"z_{metric}"] = np.nan
                    df.loc[valid_mask, f"z_{metric}"] = (df.loc[valid_mask, metric] - mean_val) / std_val
                else:
                    df[f"z_{metric}"] = 0.0
            else:
                df[f"z_{metric}"] = 0.0
    
    # Calculate weighted composite score
    # Note: For lap_time_mean, lap_time_std, pit_time, and teammate_delta,
    # we negate the z-score because lower is better (faster times = better)
    # Fastest lap indicator is already normalized (0 or 1)
    df["performance_score"] = (
        0.28 * df["z_position_gain"].fillna(0) +
        0.23 * (-df["z_lap_time_mean"].fillna(0)) +
        0.18 * (-df["z_lap_time_std"].fillna(0)) +
        0.13 * (-df["z_pit_time"].fillna(0)) +
        0.08 * (-df["z_teammate_delta"].fillna(0)) +
        0.10 * df["fastest_lap_indicator"].fillna(0)
    )
    
    # Round to 3 decimal places
    df["performance_score"] = df["performance_score"].round(3)
    
    return df


def _get_driver_id_map(season: int, round_no: int) -> dict:
    """Get mapping from driver name to driverId."""
    url = f"{BASE_URL}/{season}/{round_no}/results.json"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    
    races = data["MRData"]["RaceTable"]["Races"]
    if not races:
        return {}
    
    results = races[0]["Results"]
    driver_map = {}
    
    for r in results:
        driver_id = r["Driver"]["driverId"]
        driver_name = f'{r["Driver"]["givenName"]} {r["Driver"]["familyName"]}'
        driver_map[driver_name] = driver_id
    
    return driver_map


def _calculate_teammate_delta(df: pd.DataFrame) -> pd.Series:
    """
    Calculate time difference from teammate.
    For each driver, find their teammate (same constructor) and calculate time delta.
    Uses actual race times if available, otherwise uses position difference as proxy.
    """
    teammate_delta = pd.Series(index=df.index, dtype=float)
    
    # Try to extract actual race times from the 'time' column
    def _extract_time_seconds(time_str):
        """Extract time in seconds from time string."""
        if pd.isna(time_str) or time_str == "DNF":
            return np.nan
        if isinstance(time_str, str):
            if "lap" in time_str.lower():
                # Lapped cars - use position as proxy
                return np.nan
            try:
                # Try to parse as seconds (e.g., "5.234")
                return float(time_str)
            except ValueError:
                return np.nan
        return np.nan
    
    df["time_seconds"] = df["time"].apply(_extract_time_seconds)
    
    for constructor in df["constructor"].unique():
        teammates = df[df["constructor"] == constructor].copy()
        
        if len(teammates) < 2:
            # No teammate, set delta to 0
            teammate_delta.loc[teammates.index] = 0.0
            continue
        
        # Sort by finish position
        finish_col = pd.to_numeric(teammates["Finish"], errors='coerce')
        teammates_sorted = teammates.copy()
        teammates_sorted["finish_numeric"] = finish_col
        teammates_sorted = teammates_sorted.sort_values("finish_numeric")
        
        team_leader_idx = teammates_sorted.index[0]
        leader_time = teammates_sorted.loc[team_leader_idx, "time_seconds"]
        
        for idx, row in teammates.iterrows():
            if idx == team_leader_idx:
                # Team leader gets 0
                teammate_delta.loc[idx] = 0.0
            else:
                driver_time = row["time_seconds"]
                
                if pd.notna(leader_time) and pd.notna(driver_time):
                    # Use actual time difference
                    time_diff = driver_time - leader_time
                    teammate_delta.loc[idx] = float(time_diff)
                else:
                    # Fall back to position difference as proxy
                    row_finish = pd.to_numeric(row["Finish"], errors='coerce')
                    leader_finish = pd.to_numeric(teammates_sorted.iloc[0]["Finish"], errors='coerce')
                    
                    if pd.notna(row_finish) and pd.notna(leader_finish):
                        position_diff = row_finish - leader_finish
                        teammate_delta.loc[idx] = float(position_diff)
                    else:
                        teammate_delta.loc[idx] = 0.0
    
    return teammate_delta


def _calculate_fastest_lap_indicator(df: pd.DataFrame, season: int, round_no: int) -> pd.Series:
    """
    Calculate fastest lap indicator (1 if driver has fastest lap, 0 otherwise).
    """
    fastest_lap_indicator = pd.Series(index=df.index, dtype=float)
    fastest_lap_indicator[:] = 0.0
    
    # Fetch race results to get fastest lap data
    url = f"{BASE_URL}/{season}/{round_no}/results.json"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    
    races = data["MRData"]["RaceTable"]["Races"]
    if not races:
        return fastest_lap_indicator
    
    results = races[0]["Results"]
    
    # Find the overall fastest lap time
    fastest_lap_time_seconds = None
    fastest_lap_driver_id = None
    
    def parse_lap_time(time_str):
        """Convert lap time string to seconds for comparison."""
        if not time_str or time_str == "":
            return None
        try:
            if ":" in time_str:
                parts = time_str.split(":")
                minutes = float(parts[0])
                seconds = float(parts[1])
                return minutes * 60 + seconds
            else:
                return float(time_str)
        except (ValueError, IndexError):
            return None
    
    for r in results:
        fastest_lap_data = r.get("FastestLap", {})
        if fastest_lap_data and "Time" in fastest_lap_data:
            lap_time_str = fastest_lap_data["Time"].get("time", "")
            lap_time_seconds = parse_lap_time(lap_time_str)
            
            if lap_time_seconds is not None:
                if fastest_lap_time_seconds is None or lap_time_seconds < fastest_lap_time_seconds:
                    fastest_lap_time_seconds = lap_time_seconds
                    fastest_lap_driver_id = r["Driver"]["driverId"]
    
    # Set indicator to 1 for the driver with fastest lap
    if fastest_lap_driver_id:
        fastest_lap_indicator[df["driverId"] == fastest_lap_driver_id] = 1.0
    
    return fastest_lap_indicator
