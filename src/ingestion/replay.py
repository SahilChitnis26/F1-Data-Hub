"""
Track replay: time-series X/Y positions for drivers over a lap range.
Uses FastF1 session telemetry (position data), resampled to a uniform timeline.
Returns: timeline_ms, series { "<CODE>": { x, y } }, and optional error field.
"""

import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd
import fastf1

from .deep_analysis import UnsupportedSessionError

logger = logging.getLogger(__name__)


def _is_timedelta64_dtype(dtype) -> bool:
    """True if dtype is timedelta64 (any resolution). Compatible across pandas versions."""
    if hasattr(pd.api.types, "is_timedelta64_any_dtype"):
        return pd.api.types.is_timedelta64_any_dtype(dtype)
    if hasattr(pd.api.types, "is_timedelta64_ns_dtype"):
        return pd.api.types.is_timedelta64_ns_dtype(dtype)
    return False


def to_ms(x):
    """
    Convert timedelta-like values to a list of integers (milliseconds).
    Handles: pd.Series (timedelta64), np.ndarray (timedelta64), datetime.timedelta, list[int].
    Returns list[int]; pass-through for already list[int].
    """
    if x is None:
        return []
    if isinstance(x, list):
        if not x:
            return []
        first = x[0]
        if isinstance(first, (int, float)) and not isinstance(first, bool):
            return [int(v) for v in x]
        if hasattr(first, "total_seconds"):
            return [int(v.total_seconds() * 1000) for v in x]
        return [int(v) for v in x]
    if isinstance(x, pd.Series):
        if _is_timedelta64_dtype(x.dtype):
            return (x.dt.total_seconds() * 1000).astype("int64").tolist()
        if x.empty:
            return []
        return [int(v) for v in x.tolist()]
    if isinstance(x, np.ndarray):
        if x.size == 0:
            return []
        if np.issubdtype(x.dtype, np.timedelta64):
            return x.astype("timedelta64[ms]").astype("int64").tolist()
        return [int(v) for v in x.tolist()]
    if hasattr(x, "total_seconds"):
        return [int(x.total_seconds() * 1000)]
    return []


def _timedelta_to_seconds(ser_or_arr):
    """
    Convert pandas Series or numpy array of timedelta64 to float seconds (for np.interp/linspace).
    Safe for TimedeltaArray: no direct astype(float).
    """
    if isinstance(ser_or_arr, pd.Series):
        if _is_timedelta64_dtype(ser_or_arr.dtype):
            return ser_or_arr.dt.total_seconds().to_numpy(dtype=float)
        return ser_or_arr.astype(float).to_numpy()
    if isinstance(ser_or_arr, np.ndarray) and np.issubdtype(ser_or_arr.dtype, np.timedelta64):
        return ser_or_arr.astype("timedelta64[ns]").view("int64") / 1e9
    arr = np.asarray(ser_or_arr)
    if arr.size == 0:
        return np.array([], dtype=float)
    if np.issubdtype(arr.dtype, np.timedelta64):
        return arr.astype("timedelta64[ns]").view("int64") / 1e9
    return arr.astype(float)


def _normalize(s: str) -> str:
    """Uppercase, trim, collapse spaces, remove punctuation. For lookup keys."""
    if not isinstance(s, str) or pd.isna(s):
        return ""
    s = s.strip().upper()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s]", "", s)
    return s.strip()


def _safe_str(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val).strip()


def resolve_driver_ids(session, drivers_in: list[str]) -> tuple[list[str], list[str]]:
    """
    Map any input token to a FastF1 driver code (e.g. "LEC").

    Accepts: 3-letter code, driver number (str), full name, last name only.
    Uses session.results (Abbreviation, FullName, DriverNumber, LastName) with
    normalized keys. Returns (resolved_codes, warnings). Unresolved inputs
    produce warning "unknown_driver:<input>". Last name maps only if unique.
    """
    warnings: list[str] = []
    resolved: list[str] = []
    seen: set[str] = set()

    lookup: dict[str, str] = {}
    lastname_to_codes: dict[str, list[str]] = {}

    try:
        results = getattr(session, "results", None)
        if results is not None and hasattr(results, "iterrows"):
            for _, row in results.iterrows():
                abbrev = _safe_str(row.get("Abbreviation"))
                full = _safe_str(row.get("FullName"))
                num = _safe_str(row.get("DriverNumber"))
                last = _safe_str(row.get("LastName"))
                if not abbrev:
                    continue
                for key in (_normalize(abbrev), _normalize(full), _normalize(num), _normalize(last)):
                    if key:
                        lookup[key] = abbrev
                if last:
                    nlast = _normalize(last)
                    lastname_to_codes.setdefault(nlast, []).append(abbrev)
        else:
            laps = getattr(session, "laps", None)
            if laps is not None and not (hasattr(laps, "empty") and laps.empty):
                for code in laps["Driver"].dropna().unique().tolist():
                    code = str(code).strip()
                    if len(code) == 3:
                        lookup[_normalize(code)] = code
    except Exception as e:
        logger.debug("resolve_driver_ids: building lookup failed: %s", e)

    for raw in drivers_in:
        if not raw or not str(raw).strip():
            continue
        token = str(raw).strip()
        norm = _normalize(token)
        code = None
        if len(token) == 3 and norm in lookup and lookup[norm] == token.upper():
            code = token.upper()
        elif norm in lookup:
            # Last name: use only if unique
            if norm in lastname_to_codes and len(lastname_to_codes[norm]) > 1:
                warnings.append(f"unknown_driver:{token}")
                logger.debug("resolve_driver_ids: ambiguous last name %r", token)
                continue
            code = lookup[norm]
        if code and code not in seen:
            seen.add(code)
            resolved.append(code)
        else:
            if not code:
                warnings.append(f"unknown_driver:{token}")
                logger.debug("resolve_driver_ids: unresolved token %r", token)

    logger.info(
        "resolve_driver_ids: drivers_in=%s -> resolved=%s warnings=%s",
        drivers_in, resolved, warnings,
    )
    return (resolved, warnings)


def _driver_code_to_name(session_obj, code: str, laps: pd.DataFrame) -> str:
    """Resolve driver full name from session; fallback to code."""
    try:
        driver_laps = laps[laps["Driver"] == code]
        if driver_laps.empty:
            return code
        driver_number = driver_laps["DriverNumber"].iloc[0]
        if pd.isna(driver_number):
            return code
        info = session_obj.get_driver(str(int(driver_number)))
        if not info:
            return code
        if isinstance(info, dict):
            first = info.get("FirstName") or info.get("GivenName") or ""
            last = info.get("LastName") or info.get("FamilyName") or ""
            if first or last:
                return f"{first} {last}".strip() or code
            return info.get("FullName", code)
        return getattr(info, "FullName", None) or getattr(info, "Abbreviation", code) or code
    except Exception:
        return code


def _replay_cache_path() -> Path:
    """FastF1 cache dir (cross-platform)."""
    base = Path(__file__).resolve().parent.parent.parent
    return base / "data" / "FastF1Cache"


def _get_session(season: int, round_no: int):
    """Load race session with laps and telemetry (position data); uses project FastF1 cache."""
    try:
        cache_dir = _replay_cache_path()
        if cache_dir.exists() or not cache_dir.parent.exists():
            try:
                fastf1.Cache.enable_cache(str(cache_dir))
            except Exception:
                pass
    except Exception:
        pass
    try:
        session_obj = fastf1.get_session(season, round_no, "R")
        session_obj.load(laps=True, telemetry=True)
        return session_obj
    except Exception as e:
        raise UnsupportedSessionError(str(e)) from e


def fetch_track_replay(
    season: int,
    round_no: int,
    drivers: list[str],
    lap_start: int,
    lap_end: int,
    sample_hz: int = 10,
) -> dict:
    """
    Fetch time-series track positions (X, Y) for the given drivers and lap range.
    Returns a frontend-friendly payload with a shared timeline and resampled series.

    Parameters
    ----------
    season : int
        F1 season year (e.g. 2024).
    round_no : int
        Round number (1-based).
    drivers : list[str]
        Driver names or codes (e.g. ["Charles Leclerc", "VER"]); mapped to FastF1 codes.
    lap_start : int
        First lap (inclusive).
    lap_end : int
        Last lap (inclusive).
    sample_hz : int
        Target sampling frequency (Hz). Timeline step = 1000/sample_hz ms.

    Returns
    -------
    dict
        timeline_ms, series { "<CODE>": { x, y } }, meta; or error field if no data.
    """
    if not drivers:
        return _empty_replay_payload(
            season, round_no, drivers, lap_start, lap_end, sample_hz,
            warnings=["no_drivers_requested"],
        )

    session_obj = _get_session(season, round_no)
    laps = session_obj.laps
    if laps.empty:
        return _empty_replay_payload(
            season, round_no, drivers, lap_start, lap_end, sample_hz,
            warnings=["no_laps"],
        )

    requested_codes, resolution_warnings = resolve_driver_ids(session_obj, drivers)

    if not requested_codes:
        return _empty_replay_payload(
            season, round_no, list(drivers), lap_start, lap_end, sample_hz,
            warnings=resolution_warnings or ["no_drivers_resolved"],
        )

    # Collect (SessionTime, X, Y) per driver; prefer telemetry X/Y, fallback to get_pos_data()
    driver_telemetry: dict[str, pd.DataFrame] = {}
    laps_count_per_driver: dict[str, int] = {}
    telemetry_len_per_driver: dict[str, int] = {}
    all_warnings: list[str] = list(resolution_warnings)

    for code in requested_codes:
        try:
            driver_laps = session_obj.laps.pick_driver(code)
        except Exception:
            driver_laps = pd.DataFrame()
        if hasattr(driver_laps, "empty") and driver_laps.empty:
            continue
        driver_laps = driver_laps[
            (driver_laps["LapNumber"] >= lap_start)
            & (driver_laps["LapNumber"] <= lap_end)
        ].sort_values("LapNumber")
        if driver_laps.empty:
            continue
        laps_count_per_driver[code] = len(driver_laps)
        parts = []
        for _, lap in driver_laps.iterrows():
            try:
                tel = lap.get_telemetry()
                df_xy = None
                if tel is not None and not tel.empty and "SessionTime" in tel.columns:
                    if "X" in tel.columns and "Y" in tel.columns:
                        df_xy = pd.DataFrame({
                            "SessionTime": tel["SessionTime"].values,
                            "X": pd.to_numeric(tel["X"], errors="coerce"),
                            "Y": pd.to_numeric(tel["Y"], errors="coerce"),
                        })
                if df_xy is None:
                    pos = lap.get_pos_data()
                    if pos is not None and not pos.empty and "SessionTime" in pos.columns and "X" in pos.columns and "Y" in pos.columns:
                        df_xy = pd.DataFrame({
                            "SessionTime": pos["SessionTime"].values,
                            "X": pd.to_numeric(pos["X"], errors="coerce"),
                            "Y": pd.to_numeric(pos["Y"], errors="coerce"),
                        })
                if df_xy is not None and not df_xy.empty:
                    df_xy = df_xy.dropna(subset=["SessionTime", "X", "Y"])
                    if not df_xy.empty:
                        parts.append(df_xy)
            except Exception:
                continue
        if not parts:
            continue
        combined = pd.concat(parts, ignore_index=True)
        combined = combined.dropna(subset=["SessionTime", "X", "Y"])
        combined = combined.sort_values("SessionTime").drop_duplicates(
            subset=["SessionTime"], keep="first"
        )
        if not combined.empty:
            driver_telemetry[code] = combined
            telemetry_len_per_driver[code] = len(combined)

    total_laps_found = sum(laps_count_per_driver.values())
    total_points = sum(telemetry_len_per_driver.values())
    logger.info(
        "replay: resolved_codes=%s laps_count_per_driver=%s points_per_driver=%s total_points=%s",
        requested_codes, laps_count_per_driver, telemetry_len_per_driver, total_points,
    )

    if not driver_telemetry:
        if requested_codes and total_laps_found == 0:
            all_warnings.append("no_laps_in_range")
        elif requested_codes and total_laps_found > 0:
            all_warnings.append("no_pos_data")
        all_warnings.extend([f"no_telemetry:{c}" for c in requested_codes if c not in driver_telemetry])
        return _empty_replay_payload(
            season, round_no, list(drivers), lap_start, lap_end, sample_hz,
            warnings=all_warnings,
        )

    # Shared time range; downsample to sample_hz (uniform timeline)
    all_starts = []
    all_ends = []
    for df in driver_telemetry.values():
        st = df["SessionTime"]
        sec = _timedelta_to_seconds(st)
        all_starts.append(sec.min())
        all_ends.append(sec.max())
    t0_sec = min(all_starts)
    t1_sec = max(all_ends)
    duration_sec = max(0.0, t1_sec - t0_sec)
    step_sec = 1.0 / sample_hz
    n_samples = max(1, int(round(duration_sec / step_sec)) + 1)
    timeline_sec = np.linspace(t0_sec, t1_sec, n_samples)
    # Uniform time base in ms (0, step_ms, 2*step_ms, ...)
    step_ms = 1000 // sample_hz
    timeline_ms = [i * step_ms for i in range(n_samples)]
    if not timeline_ms:
        timeline_ms = []
        all_warnings.append("empty_timeline")
        logger.warning("replay: empty timeline for race_id=%s lap_start=%s lap_end=%s", season, round_no, lap_start, lap_end)

    def to_float_list(arr: np.ndarray) -> list[float]:
        return [float(round(v, 4)) for v in arr]

    series: dict[str, dict[str, list[float]]] = {}
    for code in requested_codes:
        if code not in driver_telemetry:
            continue
        df = driver_telemetry[code]
        st = df["SessionTime"]
        t_sec = _timedelta_to_seconds(st)
        x_vals = df["X"].to_numpy(dtype=float)
        y_vals = df["Y"].to_numpy(dtype=float)
        x_resampled = np.interp(timeline_sec, t_sec, x_vals)
        y_resampled = np.interp(timeline_sec, t_sec, y_vals)
        series[code] = {
            "x": to_float_list(x_resampled),
            "y": to_float_list(y_resampled),
        }

    downsampled_length = len(timeline_ms)
    logger.info(
        "replay: downsampled_length=%s (sample_hz=%s) points_count=%s",
        downsampled_length, sample_hz, total_points,
    )

    # Track polyline from reference lap (fastest lap in range among drivers with telemetry)
    track_x: list[float] = []
    track_y: list[float] = []
    ref_laps_in_range = laps[
        (laps["LapNumber"] >= lap_start) & (laps["LapNumber"] <= lap_end)
        & laps["Driver"].isin(driver_telemetry.keys())
    ]
    if not ref_laps_in_range.empty and "LapTime" in ref_laps_in_range.columns:
        valid = ref_laps_in_range.dropna(subset=["LapTime"])
        if not valid.empty:
            ref_lap = valid.loc[valid["LapTime"].idxmin()]
            try:
                ref_tel = ref_lap.get_telemetry()
                ref_df = None
                if ref_tel is not None and not ref_tel.empty and "X" in ref_tel.columns and "Y" in ref_tel.columns and "SessionTime" in ref_tel.columns:
                    ref_df = pd.DataFrame({
                        "SessionTime": ref_tel["SessionTime"].values,
                        "X": pd.to_numeric(ref_tel["X"], errors="coerce"),
                        "Y": pd.to_numeric(ref_tel["Y"], errors="coerce"),
                    })
                if ref_df is None:
                    ref_pos = ref_lap.get_pos_data()
                    if ref_pos is not None and not ref_pos.empty and "X" in ref_pos.columns and "Y" in ref_pos.columns and "SessionTime" in ref_pos.columns:
                        ref_df = pd.DataFrame({
                            "SessionTime": ref_pos["SessionTime"].values,
                            "X": pd.to_numeric(ref_pos["X"], errors="coerce"),
                            "Y": pd.to_numeric(ref_pos["Y"], errors="coerce"),
                        })
                if ref_df is not None:
                    ref_df = ref_df.dropna(subset=["SessionTime", "X", "Y"])
                    if not ref_df.empty:
                        track_x = to_float_list(ref_df["X"].to_numpy(dtype=float))
                        track_y = to_float_list(ref_df["Y"].to_numpy(dtype=float))
            except Exception as e:
                logger.debug("replay: reference lap XY failed: %s", e)
    if not track_x and not track_y and series:
        first_code = next((c for c in requested_codes if c in series), None)
        if first_code:
            track_x, track_y = series[first_code]["x"], series[first_code]["y"]

    drivers_by_name: dict[str, dict[str, list[float]]] = {}
    for code in requested_codes:
        if code not in series:
            continue
        data = series[code]
        name = _driver_code_to_name(session_obj, code, laps)
        drivers_by_name[name] = {"x": data["x"], "y": data["y"]}

    missing = [c for c in requested_codes if c not in series]
    meta: dict = {
        "race_id": f"{season}_{round_no}",
        "lap_start": lap_start,
        "lap_end": lap_end,
        "sample_hz": sample_hz,
        "laps_found": total_laps_found,
        "telemetry_len_per_driver": telemetry_len_per_driver,
        "downsampled_length": downsampled_length,
    }
    if all_warnings or missing:
        meta["warnings"] = all_warnings + [f"no_telemetry:{c}" for c in missing]

    return {
        "track": {"x": track_x, "y": track_y},
        "drivers": drivers_by_name,
        "meta": meta,
        "timeline_ms": to_ms(timeline_ms),
        "series": series,
    }


def _empty_replay_payload(
    season: int,
    round_no: int,
    drivers: list[str],
    lap_start: int,
    lap_end: int,
    sample_hz: int,
    warnings: list[str] | None = None,
) -> dict:
    """Empty replay payload (no telemetry or no matching drivers/laps). Includes error field."""
    meta: dict = {
        "race_id": f"{season}_{round_no}",
        "lap_start": lap_start,
        "lap_end": lap_end,
        "sample_hz": sample_hz,
    }
    if warnings:
        meta["warnings"] = warnings
    return {
        "error": "No telemetry data found",
        "track": {"x": [], "y": []},
        "drivers": {},
        "meta": meta,
        "timeline_ms": [],
        "series": {},
    }
