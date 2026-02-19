"""
Demo: Run execution score on fetch_lap_pace() output and print top 5.
Usage: python scripts/run_execution_score_demo.py [season] [round]
Default: 2024, 3 (Australian GP).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ingestion.deep_analysis import fetch_lap_pace
from src.scoring.execution_score import calculate_execution_score


def main():
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2024
    round_no = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    print(f"Fetching lap pace for {season} Round {round_no}...")
    laps_df = fetch_lap_pace(season, round_no)
    if laps_df.empty:
        print("No lap data available.")
        return

    print(f"Computing execution score ({len(laps_df)} laps)...")
    result = calculate_execution_score(laps_df)

    # Ensure no NaNs in execution_score
    assert result["execution_score"].notna().all(), "execution_score must have no NaNs"

    top5 = result.nlargest(5, "execution_score")[
        ["driver", "execution_score", "pace_med_delta", "consistency_mad", "deg_slope", "pit_loss_proxy"]
    ]
    print("\n--- Top 5 Execution Score ---")
    print(top5.to_string(index=False))
    print(f"\n(Total drivers: {len(result)})")


if __name__ == "__main__":
    main()
