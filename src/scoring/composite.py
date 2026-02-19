"""
Unified composite score: blends Results Score and Execution Score.

Composite is a wrapper—it takes pre-computed results_df and optional execution_df,
merges on consistent driver keys (FastF1-style 3-letter code), and returns
driver, results_score, execution_score (optional), composite_score.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Optional

# Weights for blend when execution is present
WEIGHT_RESULTS = 0.4
WEIGHT_EXECUTION = 0.6

# Ergast driverId (lowercase) -> FastF1 3-letter code. Covers current/recent grid.
ERGAST_DRIVER_ID_TO_CODE: dict[str, str] = {
    "alonso": "ALO",
    "albon": "ALB",
    "bottas": "BOT",
    "gasly": "GAS",
    "hamilton": "HAM",
    "hulkenberg": "HUL",
    "kevin_magnussen": "MAG",
    "kmag": "MAG",
    "leclerc": "LEC",
    "max_verstappen": "VER",
    "norris": "NOR",
    "perez": "PER",
    "piastri": "PIA",
    "ricciardo": "RIC",
    "russell": "RUS",
    "sainz": "SAI",
    "stroll": "STR",
    "tsunoda": "TSU",
    "magnussen": "MAG",
    "ocon": "OCO",
    "zhou": "ZHO",
    "lawson": "LAW",
    "doohan": "DOO",
    "bearman": "BEA",
    "antonelli": "ANT",
    "verstappen": "VER",
}


def _normalize_driver_code(results_df: pd.DataFrame) -> pd.Series:
    """
    Produce a Series of driver codes (FastF1-style, e.g. NOR, VER) aligned to results_df index.

    Precedence:
    1. Column 'driver_code' if present.
    2. Map 'driverId' via ERGAST_DRIVER_ID_TO_CODE (lowercase key).
    3. If 'driver' is already 3-letter uppercase, use as code.
    4. Else try mapping 'driver' as driverId (lowercase, no spaces).
    """
    n = len(results_df)
    out = pd.Series("", index=results_df.index, dtype=object)

    if "driver_code" in results_df.columns:
        out = results_df["driver_code"].astype(str).str.strip().str.upper()
        return out

    if "driverId" in results_df.columns:
        mapped = results_df["driverId"].astype(str).str.strip().str.lower().map(ERGAST_DRIVER_ID_TO_CODE)
        valid = mapped.notna() & (mapped != "")
        out.loc[valid] = mapped.loc[valid].str.upper()
        if valid.all():
            return out

    if "driver" in results_df.columns:
        dr = results_df["driver"].astype(str).str.strip()
        # Already 3-letter uppercase code?
        looks_like_code = (dr.str.len() == 3) & dr.str.isupper() & dr.str.isalpha()
        out.loc[looks_like_code] = dr.loc[looks_like_code]
        # For rest: try as driverId (e.g. "norris" -> NOR)
        unmapped = ~looks_like_code & (out == "")
        if unmapped.any():
            by_id = dr.loc[unmapped].str.lower().str.replace(" ", "_", regex=False).map(ERGAST_DRIVER_ID_TO_CODE)
            valid = by_id.notna() & (by_id.astype(str).str.strip() != "")
            out.loc[unmapped & valid] = by_id.loc[unmapped & valid].astype(str).str.strip().str.upper()

    return out


def calculate_composite(
    results_df: pd.DataFrame,
    execution_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Blend Results Score and (optionally) Execution Score into a unified composite.

    Uses consistent driver keys: FastF1-style 3-letter code (e.g. NOR, VER).
    Ergast driverId or full name in results_df is mapped to code when needed.

    Parameters
    ----------
    results_df : pd.DataFrame
        Must contain at least 'results_score'. May contain 'driver', 'driverId',
        or 'driver_code'. Driver keys are normalized to 3-letter code for merge.
    execution_df : pd.DataFrame, optional
        Per-driver execution scores. Must have 'driver' (3-letter code) and
        'execution_score'. If None, composite = results_score only.

    Returns
    -------
    pd.DataFrame
        Columns: driver (code), results_score, execution_score (optional),
        composite_score. One row per driver from results_df; no duplicates.
        When execution_df is missing, execution_score column is omitted.
    """
    if results_df.empty:
        cols = ["driver", "results_score", "composite_score"]
        if execution_df is not None and not execution_df.empty:
            cols.insert(2, "execution_score")
        return pd.DataFrame(columns=cols)

    if "results_score" not in results_df.columns:
        raise ValueError("results_df must contain 'results_score'")

    # Normalize driver to code for merge
    driver_code = _normalize_driver_code(results_df)
    base = pd.DataFrame({
        "driver": driver_code,
        "results_score": results_df["results_score"].values,
    }, index=results_df.index)

    # One row per driver (take first if duplicates)
    base = base.drop_duplicates(subset=["driver"], keep="first").reset_index(drop=True)
    # Drop rows with empty driver code (should not happen if mapping is complete)
    base = base[base["driver"].astype(str).str.len() >= 2].copy()

    if execution_df is None or execution_df.empty:
        base["composite_score"] = base["results_score"].round(3)
        return base[["driver", "results_score", "composite_score"]]

    # Dedupe execution by driver so merge does not duplicate rows
    exec_clean = execution_df[["driver", "execution_score"]].drop_duplicates(subset=["driver"], keep="first")
    exec_clean["driver"] = exec_clean["driver"].astype(str).str.strip().str.upper()

    # Left merge: keep all drivers from results; execution_score NaN when no match
    merged = base.merge(
        exec_clean,
        on="driver",
        how="left",
        suffixes=("", "_exec"),
    )
    if "execution_score_exec" in merged.columns:
        merged = merged.drop(columns=["execution_score_exec"], errors="ignore")
    if "execution_score" not in merged.columns:
        merged["execution_score"] = np.nan

    # composite = 0.4*results + 0.6*execution when execution present, else results
    has_exec = merged["execution_score"].notna()
    merged["composite_score"] = np.where(
        has_exec,
        WEIGHT_RESULTS * merged["results_score"] + WEIGHT_EXECUTION * merged["execution_score"],
        merged["results_score"],
    )
    merged["composite_score"] = merged["composite_score"].round(3)

    return merged[["driver", "results_score", "execution_score", "composite_score"]]
