# Formula One Performance Dashboard

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18+-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5+-3178C6?logo=typescript&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/TailwindCSS-3+-38B2AC?logo=tailwindcss&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)
![FastF1](https://img.shields.io/badge/Data-FastF1-orange)
![Ergast](https://img.shields.io/badge/Data-Ergast-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)

A **local, web-based dashboard** for analyzing **Formula One races, seasons, and driver performance** using both **results data** and **lap-level execution metrics**.

This project combines historical race results (1950–present) with modern lap-by-lap analysis from **FastF1** to move beyond finishing position and quantify **how well a driver actually drove the race**.

---

## Installation & Quick Start

### Option 1: Docker

The easiest way to run the dashboard without installing Python locally.

**Prerequisites**
- Docker Desktop

```bash
docker compose up --build
```

Open:
```
http://localhost:8000
```

Stop the app:
```bash
docker compose down
```

---

### Option 2: Python (Local)

Install backend dependencies:

```bash
pip install -r requirements.txt
```

---

## Running the Dashboard

### One-Step (Build + Run)

```bash
run_dashboard.bat
```

This builds the React frontend and starts the FastAPI backend.

Open:
```
http://127.0.0.1:8000
```

---

### Manual Run

```bash
cd frontend
npm run build
cd ..
python api.py
```

Or using Uvicorn:

```bash
uvicorn api:app --reload --host 127.0.0.1 --port 8000
```

> If port 8000 is in use, change it in `api.py`.

The dashboard and API are served from the same server:
```
http://127.0.0.1:8000
```

---

## Key Capabilities

### Race Analysis
- View race results by **finish position** for any season from **1950–2025**
- Sort races by **performance score** instead of classification
- Highlight fastest laps and key race outcomes

### Lap-Level Performance (FastF1)
- Full **lap-by-lap pace analysis**
- Visualize:
  - Pace trends
  - Pit stops and pit impact
  - Tire stints and degradation
  - Driver execution independent of finishing position

### Track Replay & Visualization
- Interactive **circuit track map** rendered from FastF1 positional data
- Replay driver positions in real time with adjustable playback speed
- Compare multiple drivers simultaneously with color-coded overlays
- Scrubbable timeline with custom lap range selection
- Automatic track normalization for consistent orientation across circuits
- Clean, responsive canvas rendering integrated into the main dashboard


## Planned Features

- **Live race analysis**
  - Live pace deltas
  - Real-time performance ranking
  - Tyre stint effectiveness during the race
- **Expanded tyre modeling**
  - Stint effectiveness across all races (1950–2025)

- **Season & Driver Views**
  - Full-season breakdown of:
    - Car performance trends
    - Constructor upgrades and performance shifts
  - Detailed driver profiles:
    - Teammate comparisons
    - Strengths and weaknesses derived from data
  - Constructor dashboards:
    - Average performance score
    - Reliability metrics
  -  Strategy and pit efficiency

---

## Performance Scoring Overview (WIP)

Performance is split into two layers:

### Results Score
Outcome-based performance using:
- Grid → finish delta
- Finishing outcome / points
- Teammate result comparison

### Execution Score
Lap-level race execution using:
- Pace delta vs race-median clean laps
- Consistency and variance
- Stint and degradation behavior
- Pit stop impact

**Composite Score**

```
Composite Score = 0.4 × Results Score + 0.6 × Execution Score
```

If lap-level data is unavailable, the score falls back to **Results Score only**.

---

## Pace Metric (Core Methodology)

The primary lap-level metric is **pace delta vs race-median clean laps**.

### Definition

```
pace_delta = actual lap time − expected lap time (seconds)
```

- Negative → overperformance  
- Positive → underperformance  
- Lap 1 is excluded (no baseline)

### Clean Laps
Only “clean” laps are used to build the baseline:
- Lap ≥ 2
- Not pit-in or pit-out
- Green track status (no SC / VSC / red)
- Lap time within reasonable percentile bounds

### Expected Pace
- Rolling median of clean laps (lap −2 to +2 window)
- Separate baselines for **slick** and **wet/intermediate** tyres
- Tyre regimes are never mixed

### Design Goals
- Deterministic
- Explainable
- Robust to track evolution and mixed conditions
- No ML (optional later)

---

## React Dashboard

An optional React-based dashboard lives in `frontend/` and uses:

- **React + TypeScript**
- **Tailwind CSS**
- **shadcn/ui**
- **Recharts**

UI primitives live in:
```
src/components/ui
```

Feature-specific components (charts, views) live in separate folders.

### Development Mode

```bash
cd frontend
npm install
npm run dev
```

- React dev server: `http://localhost:5173`
- API proxy: `http://127.0.0.1:8000`

---

## API Endpoints

### `GET /`
Serves the dashboard UI.

### `GET /api/race/{season}/{round_no}`
Returns race results sorted by finish position.

### `GET /api/race/{season}/{round_no}/performance`
Returns race results sorted by performance score.

---

## Tech Stack

**Backend**
- FastAPI (Python)
- pandas
- FastF1
- Ergast (gap filling only)

**Frontend**
- Vanilla HTML/CSS/JS (legacy dashboard)
- React + TypeScript + Tailwind + shadcn + Recharts

---

## Design Principles

- FastF1 is authoritative for lap-level data
- Ergast fills historical gaps only
- Deterministic and explainable metrics
- Robust to SC/VSC and mixed conditions
- ML added later as optional enhancement

---

## Notes

- Internet connection required
- Older races may have incomplete data
- Robust scaling (median/MAD, winsorization)
- Metrics and weights may evolve
- Batch files included for Windows users who are not using Docker

---

## Data Sources

- **FastF1**
- **Ergast**

This project is **not affiliated** with Formula 1, the FIA, or any data provider.

---

## License

MIT License

