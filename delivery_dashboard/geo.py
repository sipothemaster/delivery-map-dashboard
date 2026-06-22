from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pandas as pd


def read_geojson(path_text: str) -> dict | None:
    if not path_text:
        return None
    path = Path(path_text)
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def feature_properties(geojson: dict) -> Iterable[dict]:
    for feature in geojson.get("features", []):
        yield feature.get("properties") or {}


def detect_area_id_property(geojson: dict, preferred: list[str]) -> str | None:
    sample_props = list(feature_properties(geojson))[:50]
    if not sample_props:
        return None
    keys = set().union(*(props.keys() for props in sample_props))
    for key in preferred:
        if key in keys:
            return key
    lowered = {str(key).lower(): key for key in keys}
    for key in preferred:
        found = lowered.get(key.lower())
        if found:
            return found
    return None


def geojson_area_ids(geojson: dict, property_name: str) -> set[str]:
    return {
        str(props.get(property_name))
        for props in feature_properties(geojson)
        if props.get(property_name) is not None
    }


def combine_geojsons(items: list[tuple[dict | None, str | None]]) -> tuple[dict | None, str]:
    features = []
    notes = []
    for geojson, area_id_property in items:
        if not geojson or not area_id_property:
            continue
        for feature in geojson.get("features", []):
            props = feature.setdefault("properties", {})
            if props.get("area_id") is None and props.get(area_id_property) is not None:
                props["area_id"] = str(props.get(area_id_property))
            if props.get("area_id") is not None:
                features.append(feature)
        notes.append(f"{len(features):,} cumulative features")
    if not features:
        return None, "no polygon file configured"
    return {"type": "FeatureCollection", "features": features}, "; ".join(notes)


def polygon_coverage(area_metrics: pd.DataFrame, polygon_ids: set[str]) -> tuple[int, int]:
    if area_metrics.empty:
        return 0, len(polygon_ids)
    metric_ids = set(area_metrics["area_id"].dropna().astype(str))
    return len(metric_ids & polygon_ids), len(polygon_ids)
