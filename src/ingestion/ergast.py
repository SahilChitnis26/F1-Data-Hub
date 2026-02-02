import requests
import pandas as pd

BASE_URL = "https://api.jolpi.ca/ergast/f1"


# Gather Race results from Ergast (Jolpica mirror) F1 API
def fetch_race_results(season: int, round_no: int) -> pd.DataFrame:
    """
    Fetch race results for a given season and round from the Ergast F1 API.
    Returns a tidy DataFrame (one row per driver).

    UI conventions enforced here:
      - Status column: "Finished" or "DNF"
      - Time column:
          * Leader: "0.000"
          * Same-lap finishers: time gap in seconds (e.g. "5.553")
          * Lapped finishers: "+1 Lap" / "+2 Laps" (etc.)
          * DNFs: "-"
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

    # First pass: find leader's time and laps (P1 who finished)
    for r in results:
        finish_position = int(r["position"])
        status_raw = (r.get("status", "") or "").strip()
        time_data = r.get("Time")

        if finish_position == 1 and status_raw == "Finished":
            if time_data and "millis" in time_data:
                leader_time_ms = float(time_data["millis"])
            leader_laps = int(r.get("laps", 0))
            break

    # Second pass: build rows with display status + time
    for r in results:
        finish_position = int(r["position"])
        status_raw = (r.get("status", "") or "").strip()
        time_data = r.get("Time")
        driver_laps = int(r.get("laps", 0))

        # Ergast/Jolpica encodes lapped cars as strings like "+1 Lap", "+2 Laps"
        is_lapped = status_raw.startswith("+") and "Lap" in status_raw

        # Decide display status + display time
        if is_lapped:
            status_display = "Finished"

            # Prefer computing laps down (more robust than trusting the raw string)
            if leader_laps is not None:
                laps_down = max(0, leader_laps - driver_laps)
                if laps_down == 1:
                    time_diff = "+1 Lap"
                elif laps_down > 1:
                    time_diff = f"+{laps_down} Laps"
                else:
                    # Fallback in odd edge cases
                    time_diff = status_raw or "-"
            else:
                time_diff = status_raw or "-"

        elif status_raw == "Finished":
            status_display = "Finished"

            if finish_position == 1:
                time_diff = "0.000"
            elif time_data and "millis" in time_data and leader_time_ms is not None:
                driver_time_ms = float(time_data["millis"])
                time_diff_seconds = (driver_time_ms - leader_time_ms) / 1000.0
                time_diff = f"{time_diff_seconds:.3f}"
            else:
                # Sometimes time data is missing even for finishers
                time_diff = "-"

        else:
            # Anything else is a retirement / DSQ / accident / engine / etc.
            status_display = "DNF"
            time_diff = "-"

        # Derive DNF meta for tooltips (reason + approximate lap)
        dnf_reason = ""
        dnf_lap = None
        if status_display == "DNF":
            # Use the raw Ergast status text (e.g. "Accident", "Engine", etc.)
            dnf_reason = status_raw or "Retired"

            # If we know how many laps the leader completed, approximate retirement lap
            # as "one lap after the last completed lap" for this driver.
            if leader_laps is not None and driver_laps:
                # Clamp to race distance just in case
                dnf_lap = min(driver_laps + 1, leader_laps)

        # Extract fastest lap time if available
        fastest_lap_data = r.get("FastestLap", {}) or {}
        fastest_lap_time = ""
        if "Time" in fastest_lap_data:
            fastest_lap_time = (fastest_lap_data["Time"] or {}).get("time", "")

        rows.append(
            {
                "season": season,
                "round": round_no,
                "raceName": race.get("raceName"),
                "date": race.get("date"),
                "driver": f'{r["Driver"]["givenName"]} {r["Driver"]["familyName"]}',
                "constructor": r["Constructor"]["name"],
                "grid": int(r["grid"]),
                "Finish": finish_position,
                "status": status_display,
                "time": time_diff,
                "points": float(r.get("points", 0)),
                "fastest_lap": fastest_lap_time,
                # Extra metadata for UI tooltips
                "dnf_reason": dnf_reason,
                "dnf_lap": dnf_lap,
            }
        )

    return pd.DataFrame(rows)
