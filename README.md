A web-based dashboard for analyzing Formula One races, seasons, and performance metrics, all run locally.

Main Features

View race results by finish position, or by performance based on empirical data for any year going back to 1950 up to 2025

Full season breakdown showing changes in car performance and upgrades brought by constructors (WIP)

Detailed driver profiles with all related stats and using data to analyze their drives, performance against teammates, and showing their strengths and weaknesses (WIP)

Fully detailed constructor view of their average performance score, constructor to constructor comparison, reliability, and strategy efficiency (WIP)

Shows the exact methodology used to break down performance scores using data from the races themselves (WIP)

Planned Features

Mostly involves live data gathering and running it through some metrics to see who is performing best in the race (performance ranking, live lap deltas, pace trends, tyre stints)

Tyre data race by race and the effectiveness of stints in all races from 1950 to 2025

An executable instead of running through localhost
## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

## Running the Dashboard

1. Start the FastAPI server:
```bash
python api.py
```

Or using uvicorn directly:
```bash
uvicorn api:app --reload --host 127.0.0.1 --port 8000
```
#If port 8000 is in use switch it in api.py

2. Open your browser and navigate to:
```
http://localhost:8000
```

## API Endpoints

### GET `/`
Serves the dashboard HTML page.

### GET `/api/race/{season}/{round_no}`
Get race results sorted by finish position.

**Example:**
```
GET /api/race/2024/3
```

**Response:**
```json
{
  "race_info": {
    "season": 2024,
    "round": 3,
    "raceName": "Australian GP"
  },
  "results": [
    {
      "season": 2024,
      "round": 3,
      "raceName": "Australian GP",
      "driver": "Carlos Sainz",
      "constructor": "Ferrari",
      "grid": 2,
      "Finish": 1,
      "status": "Finished",
      "time": "0.000",
      "points": 25.0,
      "fastest_lap": "1:20.031",
      "Performance": 0.919,
      "has_fastest_lap": false
    },
    ...
  ]
}
```

### GET `/api/race/{season}/{round_no}/performance`
Get race results sorted by performance score.

**Example:**
```
GET /api/race/2024/3/performance
```

## Usage

1. Enter a season year (e.g., 2024)
2. Enter a round number (e.g., 3)
3. Click "Load Race" to fetch and display results
4. Toggle between "Finish Position" and "Performance Score" views
5. The fastest lap of the race is highlighted in yellow

## Performance Score Formula

The performance score is calculated using:
- 28% Position gain (grid to finish)
- 23% Average lap time (negated)
- 18% Lap time consistency (negated)
- 13% Pit stop time (negated)
- 8% Teammate comparison (negated)
- 10% Fastest lap indicator


## Development

The dashboard uses:
- **Backend**: FastAPI (Python)
- **Frontend**: Vanilla HTML/CSS/JavaScript
- **Data**: Ergast F1 API

## Notes

- The dashboard requires an internet connection to fetch race data
- Some older races may have incomplete data
- Performance scores are calculated using z-score normalization
- Perfomance formula will be refined overtime and include new metrics it will be made so you can pick what you believe is most important
