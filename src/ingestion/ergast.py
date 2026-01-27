import requests
import pandas as pd
BASE_URL = "https://api.jolpi.ca/ergast/f1"

# Gather Race results from Ergast F1 API
def fetch_race_results(season: int, round_no: int) -> pd.DataFrame:
    """
    Fetch race results for a given season and round from the Ergast F1 API.
    Returns a tidy DataFrame (one row per driver).
    """
    url = f"{BASE_URL}/{season}/{round_no}/results.json"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    races = data["MRData"]["RaceTable"]["Races"]
    if not races:
        raise ValueError(f"No race found for season={season}, round={round_no}")

    race = races[0]
    results = race["Results"]

    rows = []
    leader_time_ms = None
    leader_laps = None
    
    # First pass: find leader's time and laps (position 1 who finished)
    for r in results:
        finish_position = int(r["position"])
        status = r.get("status", "")
        time_data = r.get("Time")
        
        # Leader is position 1, and we need their time if they finished
        if finish_position == 1 and status == "Finished":
            if time_data and "millis" in time_data:
                leader_time_ms = float(time_data["millis"])
            leader_laps = int(r.get("laps", 0))
            break
    
    # Second pass: build rows with time calculations
    for r in results:
        finish_position = int(r["position"])
        time_data = r.get("Time")
        status = r.get("status", "")
        driver_laps = int(r.get("laps", 0))
        
        # Determine time difference
        if finish_position == 1:
            # Leader always gets 0.000
            time_diff = "0.000"
        elif status == "Lapped" and leader_laps:
            # Lapped car - calculate and show laps down
            laps_down = leader_laps - driver_laps
            if laps_down == 1:
                time_diff = "+1 lap"
            else:
                time_diff = f"+{laps_down} laps"
        elif status != "Finished" and status != "Lapped":
            # Did not finish - show DNF
            time_diff = "DNF"
        elif not time_data:
            # No time data available - likely DNF
            time_diff = "DNF"
        elif "millis" in time_data and leader_time_ms:
            # Calculate time difference from leader (same lap)
            driver_time_ms = float(time_data["millis"])
            time_diff_seconds = (driver_time_ms - leader_time_ms) / 1000.0
            time_diff = f"{time_diff_seconds:.3f}"
        else:
            # No valid time data - likely DNF
            time_diff = "DNF"
        
        # Extract fastest lap time if available
        fastest_lap_data = r.get("FastestLap", {})
        fastest_lap_time = ""
        if fastest_lap_data and "Time" in fastest_lap_data:
            fastest_lap_time = fastest_lap_data["Time"].get("time", "")
        
        rows.append({
            "season": season,
            "round": round_no,
            "raceName": race.get("raceName"),
            "date": race.get("date"),
            "driver": f'{r["Driver"]["givenName"]} {r["Driver"]["familyName"]}',
            "constructor": r["Constructor"]["name"],
            "grid": int(r["grid"]),
            "Finish": finish_position,
            "status": status,
            "time": time_diff,
            "points": float(r.get("points", 0)),
            "fastest_lap": fastest_lap_time,
        })

    df = pd.DataFrame(rows)
    return df
