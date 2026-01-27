from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import pandas as pd
import os
from pathlib import Path
from src.ingestion.ergast import fetch_race_results
from src.scoring import calculate_composite_score

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


@app.get("/api/race/{season}/{round_no}")
async def get_race_results(season: int, round_no: int):
    """
    Get race results for a specific season and round.
    Returns JSON with race data including performance scores.
    """
    try:
        # Fetch race results
        df = fetch_race_results(season, round_no)
        
        # Calculate composite performance score
        df = calculate_composite_score(df, season, round_no)
        
        # Rename performance_score to Performance
        df = df.rename(columns={"performance_score": "Performance"})
        
        # Shorten race name
        df["raceName"] = df["raceName"].str.replace("Grand Prix", "GP", regex=False)
        
        # Find fastest lap
        def parse_lap_time(time_str):
            if not time_str or time_str == "":
                return float('inf')
            try:
                if ":" in time_str:
                    parts = time_str.split(":")
                    minutes = float(parts[0])
                    seconds = float(parts[1])
                    return minutes * 60 + seconds
                else:
                    return float(time_str)
            except (ValueError, IndexError):
                return float('inf')
        
        df["fastest_lap_seconds"] = df["fastest_lap"].apply(parse_lap_time)
        fastest_lap_time_seconds = df["fastest_lap_seconds"].min()
        fastest_lap_driver_idx = df[df["fastest_lap_seconds"] == fastest_lap_time_seconds].index[0] if fastest_lap_time_seconds != float('inf') else None
        
        # Convert DataFrame to dict for JSON response
        df["has_fastest_lap"] = False
        if fastest_lap_driver_idx is not None:
            df.loc[fastest_lap_driver_idx, "has_fastest_lap"] = True
        
        # Select columns for display
        display_cols = ["season", "round", "raceName", "driver", "constructor", 
                       "grid", "Finish", "status", "time", "points", "fastest_lap", 
                       "Performance", "has_fastest_lap"]
        
        df_display = df[display_cols].copy()
        
        # Convert Finish to int for proper sorting
        df_display["Finish"] = pd.to_numeric(df_display["Finish"], errors='coerce').fillna(0).astype(int)
        
        # Sort by finish position
        df_display = df_display.sort_values("Finish", ascending=True)
        
        # Check if DataFrame is empty
        if df_display.empty:
            raise HTTPException(status_code=404, detail=f"No race results found for season {season}, round {round_no}")
        
        # Convert to records (list of dicts)
        results = df_display.to_dict(orient="records")
        
        # Get race info
        race_info = {
            "season": int(df_display.iloc[0]["season"]),
            "round": int(df_display.iloc[0]["round"]),
            "raceName": df_display.iloc[0]["raceName"]
        }
        
        return JSONResponse(content={
            "race_info": race_info,
            "results": results
        })
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/race/{season}/{round_no}/performance")
async def get_race_results_performance(season: int, round_no: int):
    """
    Get race results sorted by performance score.
    """
    try:
        # Fetch race results
        df = fetch_race_results(season, round_no)
        
        # Calculate composite performance score
        df = calculate_composite_score(df, season, round_no)
        
        # Rename performance_score to Performance
        df = df.rename(columns={"performance_score": "Performance"})
        
        # Shorten race name
        df["raceName"] = df["raceName"].str.replace("Grand Prix", "GP", regex=False)
        
        # Select columns for display
        display_cols = ["season", "round", "raceName", "driver", "constructor", 
                       "grid", "Finish", "status", "time", "points", "Performance"]
        
        df_display = df[display_cols].copy()
        
        # Convert Finish to int
        df_display["Finish"] = pd.to_numeric(df_display["Finish"], errors='coerce').fillna(0).astype(int)
        
        # Sort by performance score
        df_display = df_display.sort_values("Performance", ascending=False)
        
        # Check if DataFrame is empty
        if df_display.empty:
            raise HTTPException(status_code=404, detail=f"No race results found for season {season}, round {round_no}")
        
        # Convert to records
        results = df_display.to_dict(orient="records")
        
        # Get race info
        race_info = {
            "season": int(df_display.iloc[0]["season"]),
            "round": int(df_display.iloc[0]["round"]),
            "raceName": df_display.iloc[0]["raceName"]
        }
        
        return JSONResponse(content={
            "race_info": race_info,
            "results": results
        })
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    # Run without reload when executing directly
    # For auto-reload during development, use: uvicorn api:app --reload --host 127.0.0.1 --port 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)
