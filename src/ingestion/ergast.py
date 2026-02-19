import logging
import time
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://api.jolpi.ca/ergast/f1"
LAPS_PAGE_LIMIT = 1000
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache" / "ergast"
MAX_RETRIES = 3
RETRY_BACKOFF_SEC = 2

log = logging.getLogger(__name__)


def _request_with_retry(url: str, timeout: int = 30) -> requests.Response:
    """GET with retry and backoff on 429 (rate limit)."""
    last_resp = None
    for attempt in range(MAX_RETRIES):
        resp = requests.get(url, timeout=timeout)
        last_resp = resp
        if resp.status_code == 429:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF_SEC * (attempt + 1)
                log.debug("Ergast 429 rate limit, retrying in %s s (attempt %s)", wait, attempt + 1)
                time.sleep(wait)
            else:
                resp.raise_for_status()
        else:
            resp.raise_for_status()
            return resp
    if last_resp is not None:
        last_resp.raise_for_status()
    return last_resp


def _time_string_to_seconds(time_str: str) -> float | None:
    """Parse '1:23.456' or '23.456' to seconds. Returns None on parse error."""
    if not (time_str and time_str.strip()):
        return None
    try:
        if ":" in time_str:
            parts = time_str.strip().split(":")
            return float(parts[0]) * 60 + float(parts[1])
        return float(time_str.strip())
    except (ValueError, IndexError):
        return None


def _parse_lap_times_from_response(data: dict) -> list[dict]:
    """Extract lap timing rows from Ergast laps.json response. Returns list of {lap, driverId, time_s, time_ms}."""
    races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    if not races:
        return []
    rows = []
    for lap_info in races[0].get("Laps", []):
        lap_num = int(lap_info.get("number", 0))
        for t in lap_info.get("Timings", []):
            time_str = (t.get("time") or "").strip()
            if not time_str:
                continue
            time_s = _time_string_to_seconds(time_str)
            if time_s is None:
                continue
            time_ms = time_s * 1000.0
            rows.append({
                "lap": lap_num,
                "driverId": t.get("driverId", ""),
                "time_s": time_s,
                "time_ms": time_ms,
            })
    return rows


def fetch_lap_times(season: int, round_no: int) -> pd.DataFrame:
    """
    Fetch all lap times for a race from the Ergast API with pagination.
    Returns DataFrame with columns: lap, driverId, time_s, time_ms.
    Uses on-disk cache under data/cache/ergast/ keyed by season/round.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{season}_{round_no}.csv"

    if cache_path.exists():
        df = pd.read_csv(cache_path)
        # Ensure numeric types
        df["lap"] = df["lap"].astype(int)
        df["time_s"] = pd.to_numeric(df["time_s"], errors="coerce")
        df["time_ms"] = pd.to_numeric(df["time_ms"], errors="coerce")
        log.info(
            "Ergast lap times: loaded from cache %s — rows=%s, drivers=%s, lap_min=%s, lap_max=%s",
            cache_path.name, len(df), df["driverId"].nunique(), int(df["lap"].min()), int(df["lap"].max()),
        )
        return df

    all_rows = []
    offset = 0
    while True:
        url = f"{BASE_URL}/{season}/{round_no}/laps.json?limit={LAPS_PAGE_LIMIT}&offset={offset}"
        resp = _request_with_retry(url)
        data = resp.json()
        rows = _parse_lap_times_from_response(data)
        if not rows:
            break
        all_rows.extend(rows)
        offset += LAPS_PAGE_LIMIT
        if len(rows) < LAPS_PAGE_LIMIT:
            break

    df = pd.DataFrame(all_rows)
    if df.empty:
        df = pd.DataFrame(columns=["lap", "driverId", "time_s", "time_ms"])
        log.info("Ergast lap times: no data for season=%s round=%s", season, round_no)
        return df

    total = len(df)
    drivers = df["driverId"].nunique()
    lap_min = int(df["lap"].min())
    lap_max = int(df["lap"].max())
    log.info(
        "Ergast lap times: total rows=%s, unique drivers=%s, lap min=%s, lap max=%s",
        total, drivers, lap_min, lap_max,
    )

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path, index=False)
    return df


# Gather Race results from Ergast (Jolpica mirror) F1 API FLYNN IS AWERSOME!
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
