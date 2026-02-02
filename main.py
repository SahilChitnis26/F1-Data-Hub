import pandas as pd
import argparse
import sys
from src.ingestion.ergast import fetch_race_results
from src.scoring import calculate_results_score, calculate_composite

def get_race_input(args=None):
    """Get season and round number from arguments or user input."""
    if args and args.season and args.round_no:
        return args.season, args.round_no
    
    try:
        if not args or not args.season:
            season_input = input("Enter year: ").strip()
            season = int(season_input)
        else:
            season = args.season
        
        if not args or not args.round_no:
            round_input = input("Enter racenumber: ").strip()
            round_no = int(round_input)
        else:
            round_no = args.round_no
        
        return season, round_no
    except (ValueError, KeyboardInterrupt, EOFError):
        print("\nInvalid input. Using defaults: season=2024, round=3")
        return 2024, 3


def display_race_results(season, round_no):
    """Display race results for a given season and round."""
    print(f"\nFetching data for {season} Season, Round {round_no}...")
    print()
    
    try:
        df = fetch_race_results(season, round_no)
    except Exception as e:
        raise Exception(f"Failed to fetch race results: {e}")
    
    # New flow: results_score -> (optional execution_score) -> calculate_composite
    df = calculate_results_score(df, season, round_no)
    results_df = df[["driver", "results_score"]].drop_duplicates("driver").reset_index(drop=True)
    composite_df = calculate_composite(results_df, execution_df=None)
    driver_to_composite = dict(zip(results_df["driver"], composite_df["composite_score"]))
    df["composite_score"] = df["driver"].map(driver_to_composite)
    df["Performance"] = df["composite_score"]
    
    # Shorten race name: replace "Grand Prix" with "GP"
    df["raceName"] = df["raceName"].str.replace("Grand Prix", "GP", regex=False)
    
    # Find fastest lap of the session
    def parse_lap_time(time_str):
        """Convert lap time string to seconds for comparison."""
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
    
    # Select columns to display for finish position view (with Fastest Lap instead of Performance)
    display_cols_finish = ["season", "round", "raceName", "driver", "constructor", 
                           "grid", "Finish", "status", "time", "points", "fastest_lap"]
    df_display_finish = df[display_cols_finish].copy()
    
    # Rename fastest_lap to "Fastest Lap"
    df_display_finish = df_display_finish.rename(columns={"fastest_lap": "Fastest Lap"})
    
    # Sort by Finish position (1st to last) by default
    finish_numeric = pd.to_numeric(df_display_finish["Finish"], errors='coerce')
    df_display_finish["finish_sort"] = finish_numeric
    df_display_finish = df_display_finish.sort_values("finish_sort", ascending=True)
    df_display_finish = df_display_finish.drop(columns=["finish_sort"])
    
    # Center all columns for display (both headers and values)
    def center_column(col):
        col_str = col.astype(str)
        max_width = max(len(str(col.name)), col_str.str.len().max())
        return col_str.str.center(max_width)
    
    df_display_centered = df_display_finish.apply(center_column)
    
    # Center column headers by renaming them
    for col in df_display_centered.columns:
        max_width = max(len(str(col)), df_display_centered[col].astype(str).str.len().max())
        centered_header = str(col).center(max_width)
        df_display_centered = df_display_centered.rename(columns={col: centered_header})
    
    # Display results sorted by finish position with highlighting
    print("Race Results (sorted by finish position):")
    print()
    
    # Find the row index of the fastest lap driver before centering
    fastest_lap_row_idx = None
    if fastest_lap_driver_idx is not None:
        # Find the position of this driver in the sorted display
        if fastest_lap_driver_idx in df_display_finish.index:
            row_pos = list(df_display_finish.index).index(fastest_lap_driver_idx)
            fastest_lap_row_idx = row_pos + 1  # +1 for header row
    
    # Convert to string and highlight fastest lap
    output_lines = df_display_centered.to_string(index=False).split('\n')
    
    for i, line in enumerate(output_lines):
        if i == fastest_lap_row_idx and fastest_lap_row_idx is not None:
            # Highlight the fastest lap row (using ANSI escape codes)
            print(f"\033[93m{line}\033[0m")  # Yellow highlight
        else:
            print(line)
    print()
    
    # Prompt user to see performance-based sorting
    try:
        user_input = input("View results sorted by Performance score? (y/n): ").strip().lower()
    except EOFError:
        # Handle non-interactive environments
        user_input = 'n'
    
    if user_input == 'y' or user_input == 'yes':
        # Re-sort by Performance score (use Performance column)
        display_cols_performance = ["season", "round", "raceName", "driver", "constructor", 
                                    "grid", "Finish", "status", "time", "points", "Performance"]
        df_performance = df[display_cols_performance].copy()
        df_performance = df_performance.sort_values("Performance", ascending=False)
        df_performance_centered = df_performance.apply(center_column)
        
        # Center column headers for performance view
        for col in df_performance_centered.columns:
            max_width = max(len(str(col)), df_performance_centered[col].astype(str).str.len().max())
            centered_header = str(col).center(max_width)
            df_performance_centered = df_performance_centered.rename(columns={col: centered_header})
        
        print("\nRace Results (sorted by Performance score):")
        print()
        print(df_performance_centered.to_string(index=False))


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Fetch and analyze Formula One race results')
    parser.add_argument('--season', type=int, help='Season year (e.g., 2024)')
    parser.add_argument('--round', type=int, dest='round_no', help='Round number (e.g., 3)')
    
    args = parser.parse_args()
    
    # Main loop
    while True:
        # Get season and round_no
        season, round_no = get_race_input(args)
        
        # Display race results
        try:
            display_race_results(season, round_no)
        except Exception as e:
            print(f"Error fetching race data: {e}")
            print("Please check the season and round number and try again.\n")
        
        # Reset args after first use so subsequent iterations prompt for input
        args = None
        
        # Ask if user wants to view another race
        try:
            continue_input = input("\nWould you like to view another race? (y/n): ").strip().lower()
            if continue_input not in ['y', 'yes']:
                print("\nThank you for using the Formula One Data Analyzer!")
                break
        except (KeyboardInterrupt, EOFError):
            print("\n\nThank you for using the Formula One Data Analyzer!")
            break


if __name__ == "__main__":
    main()
