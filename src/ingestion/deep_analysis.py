import numpy as np
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


# F1 API track status values (from FastF1 session.track_status / track_status_data Status column)
# See fastf1.api.track_status_data: 1=clear, 2=yellow, 4=SC, 5=Red Flag, 6=VSC, 7=VSC ending
_TRACK_STATUS_GREEN = 1
_TRACK_STATUS_YELLOW = 2
_TRACK_STATUS_SC = 4
_TRACK_STATUS_RED = 5
_TRACK_STATUS_VSC = 6


def _status_to_track_state(raw_status: int, yellow_sectors: list[int] | None = None) -> dict:
    """
    Map raw FastF1 track status (Status column) to our track_state, state_label, yellow_sectors.
    Priority: RED > SC > VSC > YELLOW > GREEN.
    """
    yellow_sectors = yellow_sectors or []
    try:
        s = int(raw_status)
    except (TypeError, ValueError):
        return {
            "track_state": "GREEN",
            "yellow_sectors": [],
            "state_label": "GREEN",
            "raw_status": raw_status,
        }
    # Priority order: red, SC, VSC, yellow, green (higher codes can override in some APIs)
    if s == _TRACK_STATUS_RED:
        return {"track_state": "RED", "yellow_sectors": [], "state_label": "RED", "raw_status": s}
    if s == _TRACK_STATUS_SC:
        return {"track_state": "SC", "yellow_sectors": [], "state_label": "SC", "raw_status": s}
    if s == _TRACK_STATUS_VSC:
        return {"track_state": "VSC", "yellow_sectors": [], "state_label": "VSC", "raw_status": s}
    if s == _TRACK_STATUS_YELLOW:
        if yellow_sectors:
            # S1, S2, S3 or S1+S2 etc.
            parts = "+".join(f"S{i}" for i in sorted(yellow_sectors))
            label = f"YELLOW {parts}"
        else:
            label = "YELLOW"
        return {"track_state": "YELLOW", "yellow_sectors": list(yellow_sectors), "state_label": label, "raw_status": s}
    # Green or unknown (e.g. 7 = VSC ending -> treat as green)
    return {"track_state": "GREEN", "yellow_sectors": [], "state_label": "GREEN", "raw_status": s}


def get_track_state_for_lap(session_obj, lap_number: int) -> tuple[str, list[int], str]:
    """
    Resolve track state for a given lap using the session's track_status (FastF1 official source).

    Returns:
        (track_state, yellow_sectors, state_label)
        track_state: one of "GREEN", "YELLOW", "SC", "VSC", "RED"
        yellow_sectors: list of sector numbers [1,2,3] if yellow with sector info, else []
        state_label: display string e.g. "GREEN", "YELLOW S1", "SC", "VSC", "RED"
    """
    mapped = derive_track_state_for_lap(lap_number, session_obj)
    return (
        mapped["track_state"],
        list(mapped.get("yellow_sectors") or []),
        mapped["state_label"],
    )


def derive_track_state_for_lap(lap_number: int, session_obj) -> dict:
    """
    Derive track state for a given lap number using the session's track_status.
    Uses the session time at the start of the first occurrence of that lap (min across drivers).
    Returns dict with track_state, yellow_sectors, state_label, raw_status (for debugging).
    """
    out = {
        "track_state": "GREEN",
        "yellow_sectors": [],
        "state_label": "GREEN",
        "raw_status": None,
    }
    status_df = getattr(session_obj, "track_status", None)
    t0 = getattr(session_obj, "t0_date", None)
    laps = getattr(session_obj, "laps", None)
    if (
        status_df is None
        or status_df.empty
        or "Status" not in status_df.columns
        or "Time" not in status_df.columns
        or t0 is None
        or laps is None
        or laps.empty
        or "Time" not in laps.columns
        or "LapTime" not in laps.columns
        or "LapNumber" not in laps.columns
    ):
        return out
    # Session time at start of this lap number (earliest across drivers)
    lap_mask = laps["LapNumber"] == lap_number
    if not lap_mask.any():
        return out
    lap_starts = laps.loc[lap_mask, "Time"] - laps.loc[lap_mask, "LapTime"]
    first_sec = (lap_starts.min() - t0).total_seconds()
    ts_time = status_df["Time"]
    if pd.api.types.is_timedelta64_dtype(ts_time):
        ts_time = ts_time.dt.total_seconds()
    else:
        ts_time = pd.to_numeric(ts_time, errors="coerce")
    idx = ts_time <= first_sec
    if not idx.any():
        return out
    last_row = status_df.loc[idx].iloc[-1]
    raw = last_row["Status"]
    try:
        raw = int(raw)
    except (TypeError, ValueError):
        return out
    sectors = []
    if "Sector" in status_df.columns and raw == _TRACK_STATUS_YELLOW:
        sec_val = last_row.get("Sector")
        if sec_val is not None and pd.notna(sec_val):
            try:
                sectors = [int(sec_val)] if isinstance(sec_val, (int, float)) else []
            except (TypeError, ValueError):
                pass
    mapped = _status_to_track_state(raw, sectors if sectors else None)
    mapped["raw_status"] = raw
    return mapped


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
                "tyre_regime",
                "stint",
                "is_pit_out_lap",
                "is_in_lap",
                "is_pit_lap",
                "is_track_green",
                "track_state",
                "yellow_sectors",
                "state_label",
                "raw_status",
            ]
        )

    # Use ALL laps (no pick_quicklaps, no valid_mask) so we show the full race.
    # FastF1 may have NaT for safety car laps; we fill from Ergast.
    lap_time_s = laps["LapTime"].dt.total_seconds()
    missing_times = lap_time_s.isna() | (lap_time_s <= 0)

    # Tyre regimes: expected lap times NEVER mix regimes.
    # SLICK → Soft, Medium, Hard  |  WET → Intermediate, Wet
    compound = laps["Compound"].astype(str).str.upper()
    tyre_regime = np.where(
        compound.isin(["INTERMEDIATE", "WET"]),
        "WET",
        "SLICK",
    )

    # Build base DataFrame with all laps
    df = pd.DataFrame(
        {
            "driver_number": laps["DriverNumber"].astype(str),
            "driver": laps["Driver"],
            "team": laps["Team"],
            "lap_number": laps["LapNumber"].astype(int),
            "lap_time_s": lap_time_s,
            "compound": laps["Compound"],
            "tyre_regime": tyre_regime,
            "stint": laps["Stint"].astype("Int64"),
            "is_pit_out_lap": laps["PitOutTime"].notna(),
            "is_in_lap": laps["PitInTime"].notna(),
            "is_pit_lap": laps["PitOutTime"].notna() | laps["PitInTime"].notna(),
        }
    )

    # Track status: green (1) = racing; SC/VSC/yellow/red; per-lap track_state and state_label
    try:
        status_df = getattr(session_obj, "track_status", None)
        t0 = getattr(session_obj, "t0_date", None)
        has_sector = (
            status_df is not None
            and "Sector" in status_df.columns
        )
        if (
            status_df is not None
            and not status_df.empty
            and "Status" in status_df.columns
            and "Time" in status_df.columns
            and t0 is not None
            and "Time" in laps.columns
            and "LapTime" in laps.columns
        ):
            # Session time (seconds) at start of each lap
            lap_start = laps["Time"] - laps["LapTime"]
            session_sec = (lap_start - t0).dt.total_seconds()
            ts_time = status_df["Time"]
            if pd.api.types.is_timedelta64_dtype(ts_time):
                ts_time = ts_time.dt.total_seconds()
            else:
                ts_time = pd.to_numeric(ts_time, errors="coerce")
            status_at_lap = np.full(len(df), 1)
            track_states = []
            yellow_sectors_list = []
            state_labels = []
            raw_status_list = []
            for i, sec in enumerate(session_sec):
                if pd.isna(sec):
                    status_at_lap[i] = 0
                    track_states.append("GREEN")
                    yellow_sectors_list.append([])
                    state_labels.append("GREEN")
                    raw_status_list.append(None)
                    continue
                idx = ts_time <= sec
                if idx.any():
                    last_row = status_df.loc[idx].iloc[-1]
                    raw = last_row["Status"]
                    try:
                        # FastF1 API may return Status as string ("1", "2", ...) or number
                        status_at_lap[i] = int(float(raw)) if raw is not None and raw != "" else 0
                    except (TypeError, ValueError):
                        status_at_lap[i] = 0
                    sectors = []
                    if has_sector and status_at_lap[i] == _TRACK_STATUS_YELLOW:
                        sec_val = last_row.get("Sector")
                        if sec_val is not None and pd.notna(sec_val):
                            try:
                                sectors = [int(sec_val)] if isinstance(sec_val, (int, float)) else []
                            except (TypeError, ValueError):
                                pass
                    mapped = _status_to_track_state(status_at_lap[i], sectors if sectors else None)
                    track_states.append(mapped["track_state"])
                    yellow_sectors_list.append(mapped["yellow_sectors"])
                    state_labels.append(mapped["state_label"])
                    raw_status_list.append(mapped.get("raw_status"))
                else:
                    track_states.append("GREEN")
                    yellow_sectors_list.append([])
                    state_labels.append("GREEN")
                    raw_status_list.append(None)
            df["is_track_green"] = np.array(status_at_lap) == 1
            df["track_state"] = track_states
            df["yellow_sectors"] = yellow_sectors_list
            df["state_label"] = state_labels
            df["raw_status"] = raw_status_list
        else:
            df["is_track_green"] = True
            df["track_state"] = "GREEN"
            df["yellow_sectors"] = [[] for _ in range(len(df))]
            df["state_label"] = "GREEN"
            df["raw_status"] = [None] * len(df)
    except Exception:
        df["is_track_green"] = True
        df["track_state"] = "GREEN"
        df["yellow_sectors"] = [[] for _ in range(len(df))]
        df["state_label"] = "GREEN"
        df["raw_status"] = [None] * len(df)

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

