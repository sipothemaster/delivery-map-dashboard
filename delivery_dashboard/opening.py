from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from delivery_dashboard.data import read_frame


ROOT = Path(__file__).resolve().parents[1]
AREA_OPENING_DIR = ROOT / "data/cache/opening_by_hour"
PARENT_OPENING_DIR = ROOT / "data/cache/parent_opening_by_hour"
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def safe_day(day: str | None) -> str:
    if day in DAYS:
        return str(day)
    return "Monday"


def safe_hour(hour: int | str | None) -> int:
    try:
        value = int(hour)
    except (TypeError, ValueError):
        return 12
    return max(0, min(23, value))


def hourly_file(directory: Path, day: str | None, hour: int | str | None) -> Path:
    return directory / f"{safe_day(day)}_{safe_hour(hour):02d}.parquet"


@lru_cache(maxsize=168)
def load_area_opening(day: str | None, hour: int | str | None) -> pd.DataFrame:
    path = hourly_file(AREA_OPENING_DIR, day, hour)
    if not path.exists():
        return pd.DataFrame(
            columns=[
                "area_id",
                "day_of_week",
                "hour_of_day",
                "open_restaurant_count",
                "open_restaurant_share",
                "opening_run_id",
            ]
        )
    df = read_frame(str(path))
    df["area_id"] = df["area_id"].astype(str)
    return df


@lru_cache(maxsize=168)
def load_parent_opening(day: str | None, hour: int | str | None) -> pd.DataFrame:
    path = hourly_file(PARENT_OPENING_DIR, day, hour)
    if not path.exists():
        return pd.DataFrame(
            columns=[
                "parent_id",
                "day_of_week",
                "hour_of_day",
                "open_restaurant_count",
                "open_restaurant_share",
                "median_open_restaurant_count",
                "median_open_restaurant_share",
                "opening_run_id",
            ]
        )
    df = read_frame(str(path))
    df["parent_id"] = df["parent_id"].astype(str)
    return df
