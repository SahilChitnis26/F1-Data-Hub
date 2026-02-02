import fastf1
import pandas as pd
import requests

from .ergast import fetch_lap_times

ERGAST_BASE = "https://api.jolpi.ca/ergast/f1"


class UnsupportedSessionError(Exception):
    """Raised when FastF1 does not support this session (e.g. pre-2018, no lap data)."""
    pass


def _fetch_ergast_driver_mapping(season: int, round_no: int) -> dict[str, str]:
    """Fetch Ergast driverId -> code mapping from results."""
    url = f"{ERGAST_BASE}/{season}/{round_no}/results.json"
    mapping = {}
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        if races:
            for r in races[0].get("Results", []):
                d = r.get("Driver", {})
                did = d.get("driverId", "")
                code = d.get("code", "")
                if did:
                    mapping[did.lower()] = code
    except Exception:
        pass
    return mapping


def fetch_lap_pace(season: int, round_no: int, session: str = "R") -> pd.DataFrame:
    """
    Fetch lap‑by‑lap pace data for a given race session using the FastF1 API.

    Parameters
    ----------
    season : int
        F1 season year (e.g. 2024).
    round_no : int
        Round number in the season (1‑based).
    session : str, optional
        Session code understood by FastF1, default is "R" (race).
        Common values: "FP1", "FP2", "FP3", "Q", "R", "SQ"

    """

    # Ensure FastF1 cache is enabled at project data folder
    try:
        fastf1.Cache.enable_cache(r"C:\Dev\Formula_One_Project\data\FastF1Cache")
    except Exception:
        # If cache is already enabled or path is invalid, ignore – FastF1 will still work
        pass

    # FastF1 accepts either a round number or a Grand Prix name as the second argument.
    try:
        session_obj = fastf1.get_session(season, round_no, session)
        session_obj.load()  # downloads and parses timing data if not cached
        laps = session_obj.laps
    except Exception as e:
        # Session not available, no lap data, or API unsupported (e.g. pre-2018)
        raise UnsupportedSessionError(str(e)) from e

    if laps.empty:
        # Return an empty frame with the expected columns
        return pd.DataFrame(
            columns=[
                "driver_number",
                "driver",
                "team",
                "lap_number",
                "lap_time_s",
                "compound",
                "stint",
                "is_pit_out_lap",
                "is_in_lap",
                "is_pit_lap",
            ]
        )

    # Use ALL laps (no pick_quicklaps, no valid_mask) so we show the full race.
    # FastF1 may have NaT for safety car laps; we fill from Ergast.
    lap_time_s = laps["LapTime"].dt.total_seconds()
    missing_times = lap_time_s.isna() | (lap_time_s <= 0)

    # Build base DataFrame with all laps
    df = pd.DataFrame(
        {
            "driver_number": laps["DriverNumber"].astype(str),
            "driver": laps["Driver"],
            "team": laps["Team"],
            "lap_number": laps["LapNumber"].astype(int),
            "lap_time_s": lap_time_s,
            "compound": laps["Compound"],
            "stint": laps["Stint"].astype("Int64"),
            "is_pit_out_lap": laps["PitOutTime"].notna(),
            "is_in_lap": laps["PitInTime"].notna(),
            "is_pit_lap": laps["PitOutTime"].notna() | laps["PitInTime"].notna(),
        }
    )

    # Fill missing lap times from Ergast (covers safety car laps, etc.)
    if missing_times.any():
        ergast_df = fetch_lap_times(season, round_no)
        mapping = _fetch_ergast_driver_mapping(season, round_no)
        if not ergast_df.empty and mapping:
            ergast_lookup = {}
            for _, row in ergast_df.iterrows():
                code = mapping.get(str(row["driverId"]).lower())
                if code:
                    ergast_lookup[(code, int(row["lap"]))] = row["time_s"]
            for idx in df.index[missing_times]:
                driver = df.at[idx, "driver"]
                lap_num = df.at[idx, "lap_number"]
                key = (driver, int(lap_num))
                if key in ergast_lookup:
                    df.at[idx, "lap_time_s"] = ergast_lookup[key]

    # Sort by driver then lap number for a clean view
    df = df.sort_values(["driver", "lap_number"]).reset_index(drop=True)
    return df

