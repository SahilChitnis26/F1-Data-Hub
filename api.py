from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
import pandas as pd
import numpy as np
from pathlib import Path
import logging
import math
import time

logger = logging.getLogger(__name__)

from src.ingestion.ergast import fetch_race_results
from src.ingestion.deep_analysis import fetch_lap_pace, UnsupportedSessionError
try:
    from src.ingestion.replay import fetch_track_replay
except Exception:
    fetch_track_replay = None  # route still registered; handler returns supported=False
from src.scoring import calculate_results_score, calculate_composite
from src.analytics.race_analyzer import compute_race_analyzer

app = FastAPI(title="Formula One Data Analyzer", version="1.0.0")

# Cache for Race Analyzer: 12h TTL, max 50 entries. Key: ANALYTICS_VERSION|season|round|session
ANALYTICS_VERSION = "1"
_CACHE_TTL_SEC = 12 * 3600
_CACHE_MAXSIZE = 50
_analyzer_cache: dict[str, tuple[dict, float]] = {}


def _analyzer_cache_get(key: str) -> dict | None:
    if key not in _analyzer_cache:
        return None
    payload, ts = _analyzer_cache[key]
    if time.monotonic() - ts > _CACHE_TTL_SEC:
        del _analyzer_cache[key]
        return None
    return payload


def _analyzer_cache_set(key: str, payload: dict) -> None:
    now = time.monotonic()
    if len(_analyzer_cache) >= _CACHE_MAXSIZE:
        oldest_key = min(_analyzer_cache, key=lambda k: _analyzer_cache[k][1])
        del _analyzer_cache[oldest_key]
    _analyzer_cache[key] = (payload, now)


# Replay track cache: same TTL/max as analyzer
_replay_cache: dict[str, tuple[dict, float]] = {}
REPLAY_VERSION = "2"  # bumped for track orientation normalization


def _replay_cache_get(key: str) -> dict | None:
    if key not in _replay_cache:
        return None
    payload, ts = _replay_cache[key]
    if time.monotonic() - ts > _CACHE_TTL_SEC:
        del _replay_cache[key]
        return None
    return payload


def _replay_cache_set(key: str, payload: dict) -> None:
    now = time.monotonic()
    if len(_replay_cache) >= _CACHE_MAXSIZE:
        oldest_key = min(_replay_cache, key=lambda k: _replay_cache[k][1])
        del _replay_cache[oldest_key]
    _replay_cache[key] = (payload, now)


# Get the directory where this script is located
BASE_DIR = Path(__file__).parent
FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"
ASSETS_DIR = FRONTEND_DIST / "assets"
INDEX_HTML = FRONTEND_DIST / "index.html"


class RaceRequest(BaseModel):
    season: int
    round_no: int


@app.get("/")
async def read_root():
    """Serve the React app index.html (production build)."""
    if not INDEX_HTML.exists():
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Frontend not built. Run: cd frontend && npm run build",
            },
        )
    return FileResponse(INDEX_HTML)


def normalize_status_and_time(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enforce UI conventions:
      - Status column only: "Finished" or "DNF"
      - Time column:
          * Lapped cars: "+1 Lap" / "+2 Laps" (etc.)
          * DNFs: "-"
          * Finishers w/out time: "-"
    """
    if "status" not in df.columns or "time" not in df.columns:
        return df

    status_raw = df["status"].fillna("").astype(str).str.strip()

    # Lapped status patterns like "+1 Lap", "+2 Laps"
    is_lapped = status_raw.str.startswith("+") & status_raw.str.contains("Lap", regex=False)

    # If lapped, move the +n Lap(s) into time (only if time isn't already that)
    df.loc[is_lapped, "time"] = status_raw[is_lapped]

    # Status for lapped cars should be Finished
    df.loc[is_lapped, "status"] = "Finished"

    # Anything not Finished becomes DNF
    # (Keep "Finished" as-is)
    not_finished = df["status"].fillna("").astype(str).str.strip() != "Finished"
    df.loc[not_finished, "status"] = "DNF"
    df.loc[not_finished, "time"] = df.loc[not_finished, "time"].replace("", "-").fillna("-")

    # Ensure empty time strings become "-"
    df["time"] = df["time"].replace("", "-").fillna("-")

    return df


def _clean_nan(obj):
    """
    Recursively replace any float('nan') values with None so JSON encoding doesn't fail.
    """
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_nan(v) for v in obj]
    return obj


@app.get("/api/race/{season}/{round_no}")
async def get_race_results(season: int, round_no: int):
    """
    Get race results for a specific season and round.
    Returns JSON with race data including performance scores.
    """
    try:
        # Fetch race results (Ergast)
        df = fetch_race_results(season, round_no)

        # Results score + composite (composite == results when no FastF1)
        df = calculate_results_score(df, season, round_no)
        df["composite_score"] = df["results_score"]

        # --- Normalize status/time (DNF red + lapped in time) ---
        df = normalize_status_and_time(df)

        # Keep Performance column for backward compat (same as composite_score)
        df["Performance"] = df["composite_score"]

        # Shorten race name
        df["raceName"] = df["raceName"].str.replace("Grand Prix", "GP", regex=False)

        # Find fastest lap
        def parse_lap_time(time_str):
            if not time_str or time_str == "":
                return float("inf")
            try:
                if ":" in time_str:
                    parts = time_str.split(":")
                    minutes = float(parts[0])
                    seconds = float(parts[1])
                    return minutes * 60 + seconds
                else:
                    return float(time_str)
            except (ValueError, IndexError):
                return float("inf")

        df["fastest_lap_seconds"] = df["fastest_lap"].apply(parse_lap_time)
        fastest_lap_time_seconds = df["fastest_lap_seconds"].min()
        fastest_lap_driver_idx = (
            df[df["fastest_lap_seconds"] == fastest_lap_time_seconds].index[0]
            if fastest_lap_time_seconds != float("inf")
            else None
        )

        df["has_fastest_lap"] = False
        if fastest_lap_driver_idx is not None:
            df.loc[fastest_lap_driver_idx, "has_fastest_lap"] = True

        # Select columns for display (include results_score and composite_score)
        display_cols = [
            "season",
            "round",
            "raceName",
            "driver",
            "constructor",
            "grid",
            "Finish",
            "status",
            "time",
            "points",
            "fastest_lap",
            "results_score",
            "composite_score",
            "Performance",
            "has_fastest_lap",
            "dnf_reason",
            "dnf_lap",
        ]

        df_display = df[display_cols].copy()

        # Replace NaN/NaT with None so JSON serialization is happy
        df_display = df_display.where(pd.notna(df_display), None)

        # Convert Finish to int for proper sorting
        df_display["Finish"] = pd.to_numeric(df_display["Finish"], errors="coerce").fillna(0).astype(int)

        # Sort by finish position
        df_display = df_display.sort_values("Finish", ascending=True)

        if df_display.empty:
            raise HTTPException(status_code=404, detail=f"No race results found for season {season}, round {round_no}")

        results = df_display.to_dict(orient="records")

        race_info = {
            "season": int(df_display.iloc[0]["season"]),
            "round": int(df_display.iloc[0]["round"]),
            "raceName": df_display.iloc[0]["raceName"],
        }

        payload = {"race_info": race_info, "results": results}
        safe_payload = _clean_nan(payload)
        return JSONResponse(content=jsonable_encoder(safe_payload))

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/race/{season}/{round_no}/performance")
async def get_race_results_performance(season: int, round_no: int):
    """
    Get race results sorted by performance score.
    """
    try:
        df = fetch_race_results(season, round_no)

        df = calculate_results_score(df, season, round_no)
        df["composite_score"] = df["results_score"]
        df = normalize_status_and_time(df)
        df["Performance"] = df["composite_score"]
        df["raceName"] = df["raceName"].str.replace("Grand Prix", "GP", regex=False)

        display_cols = [
            "season",
            "round",
            "raceName",
            "driver",
            "constructor",
            "grid",
            "Finish",
            "status",
            "time",
            "points",
            "results_score",
            "composite_score",
            "Performance",
            "dnf_reason",
            "dnf_lap",
        ]

        df_display = df[display_cols].copy()
        df_display = df_display.where(pd.notna(df_display), None)
        df_display["Finish"] = pd.to_numeric(df_display["Finish"], errors="coerce").fillna(0).astype(int)

        df_display = df_display.sort_values("composite_score", ascending=False)

        if df_display.empty:
            raise HTTPException(status_code=404, detail=f"No race results found for season {season}, round {round_no}")

        results = df_display.to_dict(orient="records")

        race_info = {
            "season": int(df_display.iloc[0]["season"]),
            "round": int(df_display.iloc[0]["round"]),
            "raceName": df_display.iloc[0]["raceName"],
        }

        payload = {"race_info": race_info, "results": results}
        safe_payload = _clean_nan(payload)
        return JSONResponse(content=jsonable_encoder(safe_payload))

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/race/{season}/{round_no}/lap-pace")
async def get_race_lap_pace(season: int, round_no: int):
    """
    Get lap-by-lap pace data for a race using FastF1 (deep analysis).
    Returns lap times per driver for the race session.
    """
    try:
        # Get race name from Ergast for consistent race_info
        df_race = fetch_race_results(season, round_no)
        race_name = str(df_race.iloc[0]["raceName"]).replace("Grand Prix", "GP") if not df_race.empty else f"Round {round_no}"

        df = fetch_lap_pace(season, round_no, session="R")
        if df.empty:
            race_info = {"season": season, "round": round_no, "raceName": race_name}
            payload = {"race_info": race_info, "laps": []}
            safe_payload = _clean_nan(payload)
            return JSONResponse(content=jsonable_encoder(safe_payload))

        # Columns to expose (all already in deep_analysis output)
        display_cols = [
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
        df_display = df[[c for c in display_cols if c in df.columns]].copy()
        df_display = df_display.where(pd.notna(df_display), None)

        laps = df_display.to_dict(orient="records")
        race_info = {"season": season, "round": round_no, "raceName": race_name}
        payload = {"race_info": race_info, "laps": laps}
        safe_payload = _clean_nan(payload)
        return JSONResponse(content=jsonable_encoder(safe_payload))

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/race_analyzer/{season}/{round_no}")
async def get_race_analyzer(
    season: int,
    round_no: int,
    refresh: int = Query(0, description="Set to 1 to bypass cache"),
):
    """
    Get race analyzer data: race meta, raw laps, scores (results_score, execution_score,
    composite_score), and computed metrics. Cached 12h; refresh=1 bypasses cache.
    """
    session = "R"
    cache_key = f"{ANALYTICS_VERSION}|{season}|{round_no}|{session}"
    if refresh != 1:
        cached = _analyzer_cache_get(cache_key)
        if cached is not None:
            return JSONResponse(content=jsonable_encoder(cached))

    try:
        df_race = fetch_race_results(season, round_no)
        race_name = (
            str(df_race.iloc[0]["raceName"]).replace("Grand Prix", "GP")
            if not df_race.empty
            else f"Round {round_no}"
        )
        race_meta = {
            "name": race_name,
            "season": season,
            "round": round_no,
        }

        try:
            df = fetch_lap_pace(season, round_no, session=session)
        except UnsupportedSessionError as e:
            return JSONResponse(
                status_code=200,
                content=jsonable_encoder({
                    "supported": False,
                    "message": str(e),
                }),
            )

        if df.empty:
            # Ergast results only: results_score + composite_score (no execution)
            df_race = calculate_results_score(df_race, season, round_no)
            df_race["composite_score"] = df_race["results_score"]
            results_list = df_race[["driver", "results_score"]].drop_duplicates("driver").to_dict(orient="records")
            composite_list = df_race[["driver", "results_score", "composite_score"]].copy()
            composite_list["execution_score"] = None
            composite_list = composite_list.drop_duplicates("driver").to_dict(orient="records")
            payload = {
                "race_meta": race_meta,
                "laps": [],
                "computed": {
                    "laps_with_delta": [],
                    "stint_summary": [],
                    "stint_ranges": [],
                    "insights": [],
                    "results_score": _clean_nan(results_list),
                    "execution_score": [],
                    "composite_score": _clean_nan(composite_list),
                },
            }
            safe_payload = _clean_nan(payload)
            if refresh != 1:
                _analyzer_cache_set(cache_key, safe_payload)
            return JSONResponse(content=jsonable_encoder(safe_payload))

        computed = compute_race_analyzer(df)

        # Results score from Ergast race results; composite = blend of results + execution
        df_race = calculate_results_score(df_race, season, round_no)
        results_df = df_race[["driver", "results_score"]].drop_duplicates("driver").reset_index(drop=True)
        execution_list = computed.get("execution_score", [])
        execution_df = pd.DataFrame(execution_list) if execution_list else None
        composite_df = calculate_composite(results_df, execution_df)
        results_list = composite_df[["driver", "results_score"]].to_dict(orient="records")
        composite_list = composite_df.to_dict(orient="records")

        # Raw laps: include track_state, yellow_sectors, state_label (pit remains separate)
        raw_cols = ["driver", "team", "lap_number", "lap_time_s", "compound", "stint"]
        if "is_pit_lap" in df.columns:
            df = df.copy()
            df["pit_lap"] = df["is_pit_lap"]
        else:
            df = df.copy()
            df["pit_lap"] = None
        raw_cols.append("pit_lap")
        for c in ("track_state", "yellow_sectors", "state_label"):
            if c in df.columns:
                raw_cols.append(c)
        df_raw = df[[c for c in raw_cols if c in df.columns]].copy()
        df_raw = df_raw.rename(columns={"lap_number": "lap"})
        df_raw = df_raw.where(pd.notna(df_raw), None)
        laps_raw = df_raw.to_dict(orient="records")
        for row in laps_raw:
            if row.get("lap") is not None:
                row["lap"] = int(row["lap"])
            if row.get("stint") is not None and pd.notna(row["stint"]):
                row["stint"] = int(row["stint"])
            if isinstance(row.get("lap_time_s"), (float, int)) and not math.isnan(row["lap_time_s"]):
                row["lap_time_s"] = round(float(row["lap_time_s"]), 4)
            # Ensure yellow_sectors is a list of ints for JSON (when present)
            if "yellow_sectors" in row and row["yellow_sectors"] is not None:
                try:
                    row["yellow_sectors"] = [int(x) for x in row["yellow_sectors"] if x is not None]
                except (TypeError, ValueError):
                    row["yellow_sectors"] = []

        payload = {
            "race_meta": race_meta,
            "laps": laps_raw,
            "computed": {
                "laps_with_delta": computed["laps_with_delta"],
                "stint_summary": computed["stint_summary"],
                "stint_ranges": computed["stint_ranges"],
                "insights": computed["insights"],
                "results_score": _clean_nan(results_list),
                "execution_score": computed.get("execution_score", []),
                "composite_score": _clean_nan(composite_list),
            },
        }
        safe_payload = _clean_nan(payload)
        if refresh != 1:
            _analyzer_cache_set(cache_key, safe_payload)
        return JSONResponse(content=jsonable_encoder(safe_payload))

    except UnsupportedSessionError as e:
        return JSONResponse(
            status_code=200,
            content=jsonable_encoder({"supported": False, "message": str(e)}),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def _parse_race_id(race_id: str) -> tuple[int, int]:
    """Parse race_id as 'season_round' (e.g. '2024_5') -> (season, round_no)."""
    try:
        parts = race_id.strip().split("_")
        if len(parts) != 2:
            raise ValueError("race_id must be 'season_round' (e.g. 2024_5)")
        season = int(parts[0])
        round_no = int(parts[1])
        if season < 2018 or season > 2030 or round_no < 1 or round_no > 30:
            raise ValueError("season or round out of reasonable range")
        return season, round_no
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _normalize_drivers(drivers: list[str]) -> list[str]:
    """Accept repeated params (?drivers=a&drivers=b) or comma-separated string; return list[str]."""
    out: list[str] = []
    for s in drivers:
        for part in s.split(","):
            p = part.strip()
            if p:
                out.append(p.upper())
    return list(dict.fromkeys(out))  # preserve order, dedupe


def build_track_transform(track_x: list, track_y: list) -> dict | None:
    """
    Build a consistent transform for track orientation normalization.
    Uses PCA on the track polyline: center, align principal axis horizontal,
    fix mirroring via signed area, and ensure first point in lower half.
    Returns None if track has too few points; otherwise dict with
    center, angle (radians), flip_y, flip_180.
    """
    track_x = np.asarray(track_x, dtype=np.float64)
    track_y = np.asarray(track_y, dtype=np.float64)
    n = len(track_x)
    if n != len(track_y) or n < 3:
        return None
    # Center
    cx, cy = float(np.mean(track_x)), float(np.mean(track_y))
    x_c = track_x - cx
    y_c = track_y - cy
    # Nx2 matrix (each row one point)
    pts = np.column_stack((x_c, y_c))
    # Covariance and eigen decomposition
    cov = np.cov(pts, rowvar=False)
    try:
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
    except np.linalg.LinAlgError:
        return None
    # Principal axis = eigenvector with largest eigenvalue (eigh returns ascending)
    ev = eigenvectors[:, -1]
    ex, ey = float(ev[0]), float(ev[1])
    # Rotation angle so principal axis becomes horizontal (positive x)
    angle = -math.atan2(ey, ex)
    c, s = math.cos(angle), math.sin(angle)
    R = np.array([[c, -s], [s, c]], dtype=np.float64)
    rotated = (R @ pts.T).T
    x_r, y_r = rotated[:, 0], rotated[:, 1]
    # Signed area (shoelace)
    area = 0.5 * np.sum(x_r[:-1] * y_r[1:] - x_r[1:] * y_r[:-1])
    if len(x_r) > 1:
        area += 0.5 * (x_r[-1] * y_r[0] - x_r[0] * y_r[-1])
    flip_y = bool(area < 0)
    if flip_y:
        y_r = -y_r
    # First point in lower half (y <= 0); if first point y > 0, rotate 180
    first_y = float(y_r[0])
    flip_180 = bool(first_y > 0)
    return {
        "center": (cx, cy),
        "angle": angle,
        "flip_y": flip_y,
        "flip_180": flip_180,
    }


def apply_track_transform(
    x: list[float],
    y: list[float],
    tf: dict,
) -> tuple[list[float], list[float]]:
    """
    Apply the transform from build_track_transform to coordinate arrays.
    Returns (x_out, y_out) as JSON-serializable lists of floats.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if x.size == 0 or y.size == 0 or x.size != y.size:
        return ([], [])
    cx, cy = tf["center"]
    angle = tf["angle"]
    flip_y = tf["flip_y"]
    flip_180 = tf["flip_180"]
    # Center
    x_c = x - cx
    y_c = y - cy
    pts = np.column_stack((x_c, y_c))
    # Rotation
    c, s = math.cos(angle), math.sin(angle)
    R = np.array([[c, -s], [s, c]], dtype=np.float64)
    out = (R @ pts.T).T
    x_out = out[:, 0].copy()
    y_out = out[:, 1].copy()
    if flip_y:
        y_out = -y_out
    if flip_180:
        x_out = -x_out
        y_out = -y_out
    return (
        [float(round(v, 4)) for v in x_out],
        [float(round(v, 4)) for v in y_out],
    )


@app.get("/api/races/{race_id}/replay/track")
async def get_replay_track(
    race_id: str,
    drivers: list[str] = Query(default=[], description="Driver codes: repeated (?drivers=a&drivers=b) or comma-separated (?drivers=VER,HAM)"),
    lap_start: int = Query(1, ge=1, le=500, description="First lap (inclusive)"),
    lap_end: int = Query(5, ge=1, le=500, description="Last lap (inclusive)"),
    sample_hz: int = Query(10, ge=1, le=50, description="Sample rate in Hz"),
    refresh: int = Query(0, description="Set to 1 to bypass cache"),
):
    """
    Get time-series track positions (X, Y) for requested drivers over a lap range.
    Returns a shared timeline (ms) and per-driver series for replay animation.
    race_id format: season_round (e.g. 2024_5).
    """
    if lap_start > lap_end:
        raise HTTPException(
            status_code=400,
            detail="lap_start must be <= lap_end",
        )
    season, round_no = _parse_race_id(race_id)
    driver_list = _normalize_drivers(drivers)

    cache_key = f"{REPLAY_VERSION}|{season}|{round_no}|{lap_start}|{lap_end}|{sample_hz}|{','.join(sorted(driver_list))}"
    if refresh != 1:
        cached = _replay_cache_get(cache_key)
        if cached is not None:
            return JSONResponse(content=jsonable_encoder(cached))

    canonical_fallback = {
        "error": "No telemetry data found",
        "track": {"x": [], "y": []},
        "drivers": {},
        "meta": {
            "race_id": race_id,
            "track_key": race_id,
            "lap_start": lap_start,
            "lap_end": lap_end,
            "sample_hz": sample_hz,
        },
        "timeline_ms": [],
        "series": {},
    }

    if fetch_track_replay is None:
        logger.info(
            "replay/track race_id=%s lap_start=%s lap_end=%s sample_hz=%s track_len=0 driver_lens=[]",
            race_id, lap_start, lap_end, sample_hz,
        )
        return JSONResponse(status_code=200, content=jsonable_encoder(canonical_fallback))

    try:
        payload = fetch_track_replay(
            season=season,
            round_no=round_no,
            drivers=driver_list,
            lap_start=lap_start,
            lap_end=lap_end,
            sample_hz=sample_hz,
        )
        track = payload.get("track") or {}
        track_x = list(track.get("x") or [])
        track_y = list(track.get("y") or [])
        # Single transform from track polyline; apply to track and all driver series
        tf = build_track_transform(track_x, track_y)
        if tf is not None:
            track_x, track_y = apply_track_transform(track_x, track_y, tf)
            payload["track"] = {"x": track_x, "y": track_y}
            for code, data in (payload.get("series") or {}).items():
                if isinstance(data, dict) and "x" in data and "y" in data:
                    x_out, y_out = apply_track_transform(
                        data.get("x") or [], data.get("y") or [], tf
                    )
                    payload["series"][code] = {"x": x_out, "y": y_out}
            for name, data in (payload.get("drivers") or {}).items():
                if isinstance(data, dict) and "x" in data and "y" in data:
                    x_out, y_out = apply_track_transform(
                        data.get("x") or [], data.get("y") or [], tf
                    )
                    payload["drivers"][name] = {"x": x_out, "y": y_out}
            meta = payload.get("meta") or {}
            meta["transform"] = {
                "angle_deg": round(math.degrees(tf["angle"]), 4),
                "flip_y": tf["flip_y"],
                "flip_180": tf["flip_180"],
            }
            payload["meta"] = meta
        track_len = len(track_x)
        driver_lens = [
            (name, len((d.get("x") or [])))
            for name, d in (payload.get("drivers") or {}).items()
        ]
        meta = payload.get("meta") or {}
        meta.setdefault("track_key", meta.get("race_id", f"{season}_{round_no}"))
        laps_found = meta.get("laps_found")
        telemetry_len_per_driver = meta.get("telemetry_len_per_driver")
        downsampled_length = meta.get("downsampled_length")
        logger.info(
            "replay/track race_id=%s lap_start=%s lap_end=%s sample_hz=%s track_len=%s driver_lens=%s "
            "laps_found=%s telemetry_len_per_driver=%s downsampled_length=%s",
            race_id, lap_start, lap_end, sample_hz, track_len, driver_lens,
            laps_found, telemetry_len_per_driver, downsampled_length,
        )
        safe = _clean_nan(payload)
        if refresh != 1 and payload.get("error") is None:
            _replay_cache_set(cache_key, safe)
        return JSONResponse(content=jsonable_encoder(safe))
    except UnsupportedSessionError:
        logger.info(
            "replay/track race_id=%s lap_start=%s lap_end=%s sample_hz=%s track_len=0 driver_lens=[] (unsupported)",
            race_id, lap_start, lap_end, sample_hz,
        )
        return JSONResponse(status_code=200, content=jsonable_encoder(canonical_fallback))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Serve React build: static assets and SPA fallback (must be after all API routes)
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """Serve index.html for client-side routes; 404 for /api/... that did not match."""
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    if INDEX_HTML.exists():
        return FileResponse(INDEX_HTML)
    return JSONResponse(
        status_code=503,
        content={"detail": "Frontend not built. Run: cd frontend && npm run build"},
    )


def _route_audit() -> None:
    """Temporary startup audit: print all registered routes (method + path)."""
    print("\n=== Route audit (method + path) ===")
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in sorted(route.methods):
                if method != "HEAD":
                    print(f"  {method:6} {route.path}")
        elif hasattr(route, "path"):
            print(f"  MOUNT  {route.path}")
    print("=== End route audit ===\n")


@app.on_event("startup")
def _startup_audit() -> None:
    _route_audit()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
