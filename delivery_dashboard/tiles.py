from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from delivery_dashboard.config import settings
from delivery_dashboard.data import read_frame
from delivery_dashboard.geo import read_geojson


ROOT = Path(__file__).resolve().parents[1]
PARENT_GEOJSON_FILE = ROOT / "data/boundaries/uk_lad_2024_bgc_simplified.geojson"
PARENT_COVERAGE_FILE = ROOT / "data/cache/parent_delivery_coverage.parquet"
AREA_COVERAGE_FILE = ROOT / settings.area_coverage_file
PARENT_LOOKUP_FILE = ROOT / "data/cache/area_parent_lookup.parquet"
CHILD_TILE_DIR = ROOT / "data/boundaries/children_by_parent"


def safe_parent_id(parent_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(parent_id))


def load_parent_coverage() -> pd.DataFrame:
    df = read_frame(str(PARENT_COVERAGE_FILE))
    df["parent_id"] = df["parent_id"].astype(str)
    return df


def load_parent_geojson() -> dict:
    return read_geojson(str(PARENT_GEOJSON_FILE))


def load_area_coverage_with_parent() -> pd.DataFrame:
    coverage = read_frame(str(AREA_COVERAGE_FILE))
    lookup = read_frame(str(PARENT_LOOKUP_FILE))
    coverage["area_id"] = coverage["area_id"].astype(str)
    lookup["area_id"] = lookup["area_id"].astype(str)
    return coverage.merge(lookup, on="area_id", how="left")


def load_child_geojson(parent_id: str) -> dict:
    path = CHILD_TILE_DIR / f"{safe_parent_id(parent_id)}.geojson"
    if not path.exists():
        return {"type": "FeatureCollection", "features": []}
    return json.loads(path.read_text(encoding="utf-8"))
