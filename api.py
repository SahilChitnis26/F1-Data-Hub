from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
import pandas as pd
from pathlib import Path
import math

from src.ingestion.ergast import fetch_race_results
from src.ingestion.deep_analysis import fetch_lap_pace
from src.scoring import calculate_composite_score
from src.analytics.race_analyzer import compute_race_analyzer

app = FastAPI(title="Formula One Data Analyzer", version="1.0.0")

# Get the directory where this script is located
BASE_DIR = Path(__file__).parent


class RaceRequest(BaseModel):
    season: int
    round_no: int


@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the dashboard HTML page."""
    dashboard_path = BASE_DIR / "dashboard.html"
    if not dashboard_path.exists():
        raise HTTPException(status_code=500, detail=f"Dashboard file not found at {dashboard_path}")
    with open(dashboard_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


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
        # Fetch race results
        df = fetch_race_results(season, round_no)

        # Calculate composite performance score (works off raw status/time)
        df = calculate_composite_score(df, season, round_no)

        # --- Normalize status/time (DNF red + lapped in time) ---
        df = normalize_status_and_time(df)

        # Rename performance_score to Performance
        df = df.rename(columns={"performance_score": "Performance"})

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

        # Select columns for display
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
            "Performance",
            "has_fastest_lap",
            # Extra DNF metadata for tooltips
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

        # Calculate composite performance score (works off raw status/time)
        df = calculate_composite_score(df, season, round_no)

        # --- Normalize status/time (DNF red + lapped in time) ---
        df = normalize_status_and_time(df)
        df = df.rename(columns={"performance_score": "Performance"})
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
            "Performance",
            # Extra DNF metadata for tooltips
            "dnf_reason",
            "dnf_lap",
        ]

        df_display = df[display_cols].copy()
        # Replace NaN/NaT with None so JSON serialization is happy
        df_display = df_display.where(pd.notna(df_display), None)
        df_display["Finish"] = pd.to_numeric(df_display["Finish"], errors="coerce").fillna(0).astype(int)

        df_display = df_display.sort_values("Performance", ascending=False)

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
async def get_race_analyzer(season: int, round_no: int):
    """
    Get race analyzer data: race meta, raw laps, and computed metrics (leader by lap,
    laps with delta, stint summary, insights) for the Race Analyzer dashboard.
    """
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

        df = fetch_lap_pace(season, round_no, session="R")
        if df.empty:
            payload = {
                "race_meta": race_meta,
                "laps": [],
                "computed": {
                    "leader_by_lap": {},
                    "laps_with_delta": [],
                    "stint_summary": [],
                    "stint_ranges": [],
                    "insights": [],
                },
            }
            safe_payload = _clean_nan(payload)
            return JSONResponse(content=jsonable_encoder(safe_payload))

        computed = compute_race_analyzer(df)

        # Raw laps: driver, team, lap, lap_time_s, compound, stint, pit_lap (nullable)
        raw_cols = ["driver", "team", "lap_number", "lap_time_s", "compound", "stint"]
        if "is_pit_lap" in df.columns:
            df = df.copy()
            df["pit_lap"] = df["is_pit_lap"]
        else:
            df = df.copy()
            df["pit_lap"] = None
        raw_cols.append("pit_lap")
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

        payload = {
            "race_meta": race_meta,
            "laps": laps_raw,
            "computed": {
                "leader_by_lap": computed["leader_by_lap"],
                "laps_with_delta": computed["laps_with_delta"],
                "stint_summary": computed["stint_summary"],
                "stint_ranges": computed["stint_ranges"],
                "insights": computed["insights"],
            },
        }
        safe_payload = _clean_nan(payload)
        return JSONResponse(content=jsonable_encoder(safe_payload))

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
