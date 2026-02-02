A web-based dashboard for analyzing Formula One races, seasons, and performance metrics, all run locally.

## Main Features

- View race results by finish position, going back to 1950 up to 2025
- Full-race lap-by-lap analysis using FastF1, highlighting pace trends, pit stops, tire stints, and driver execution beyond finishing position
- Full season breakdown showing changes in car peformance and upgrades brought by constructors (WIP)
- Detailed driver profiles with all related stats and using data to anaylze theirdrives, performance against teammates, and showing their strengths and weaknesses (WIP)
- Fully detailed constuctor view of their average performance score, constructor to conscuctor comparison reliabilty and strategy efficiency. (WIP)
- Shows the exactly methodology used to breakdown performance scores using data from the races themselves (WIP)
# Planned Features 
- Mostly involves live data gathering and running it through some metrics to see how is performing best in the race (performance ranking, Live lap deltas Pace trends ,Tyre stints)
- Tyre data race by race and the effective of stints in all races from 1950 to 2025
- An execuatable instead of runnning through localhost
## Installation (Python)

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
## If port 8000 is in use switch it in api.py

## Run with Docker

This is the easiest way to run the dashboard without installing Python locally.

### Prerequisites
- Install Docker Desktop

### Start the app
From the repo root (same folder as `docker-compose.yml`):

```bash
docker compose up --build
```
### Shutdown the app
```bash
docker docker compose down
```
## If port 8000 is in use switch it in api.py

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
### Data Sources
Race data is provided by FastF1 and Ergast/Jolpica.  
This project is not affiliated with Formula 1, FIA, or any data provider.

## License
This project is licensed under the MIT License.
