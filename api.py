from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
import pandas as pd
from pathlib import Path
import math
import time

from src.ingestion.ergast import fetch_race_results
from src.ingestion.deep_analysis import fetch_lap_pace, UnsupportedSessionError
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
