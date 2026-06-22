from __future__ import annotations

import argparse
import json
import re
import sys
import numbers
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
from shapely.geometry import Point, mapping, shape
from shapely.strtree import STRtree
from shapely.validation import make_valid

from delivery_dashboard.config import settings
from delivery_dashboard.data import read_frame


LAD_SERVICE = "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/Local_Authority_Districts_December_2024_Boundaries_UK_BGC/FeatureServer/0/query"
BOUNDARY_DIR = Path("data/boundaries")
CACHE_DIR = Path("data/cache")
CHILD_DIR = BOUNDARY_DIR / "children_by_parent"
PARENT_RAW = BOUNDARY_DIR / "uk_lad_2024_bgc.geojson"
PARENT_SIMPLIFIED = BOUNDARY_DIR / "uk_lad_2024_bgc_simplified.geojson"
PARENT_LOOKUP = CACHE_DIR / "area_parent_lookup.parquet"
PARENT_COVERAGE = CACHE_DIR / "parent_delivery_coverage.parquet"


def request_json(url: str, params: dict) -> dict:
    with urlopen(f"{url}?{urlencode(params)}", timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_lad_boundaries(page_size: int = 2000) -> dict:
    count_payload = request_json(LAD_SERVICE, {"where": "1=1", "returnCountOnly": "true", "f": "json"})
    total = int(count_payload["count"])
    features = []
    for offset in range(0, total, page_size):
        payload = request_json(
            LAD_SERVICE,
            {
                "where": "1=1",
                "outFields": "LAD24CD,LAD24NM,LAT,LONG",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "geojson",
                "resultOffset": offset,
                "resultRecordCount": page_size,
            },
        )
        features.extend(payload.get("features") or [])
        print(f"LAD fetched {len(features):,}/{total:,}", flush=True)
    for feature in features:
        props = feature.setdefault("properties", {})
        props["parent_id"] = str(props.get("LAD24CD"))
        props["parent_name"] = str(props.get("LAD24NM"))
        props["area_id"] = props["parent_id"]
    return {"type": "FeatureCollection", "features": features}


def count_points(obj) -> int:
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return 1
        return sum(count_points(item) for item in obj)
    return 0


def round_coords(obj, ndigits: int = 5):
    if isinstance(obj, tuple):
        return tuple(round_coords(list(obj), ndigits))
    if isinstance(obj, list):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(obj[0]), ndigits), round(float(obj[1]), ndigits)]
        return [round_coords(item, ndigits) for item in obj]
    return obj


def simplify_feature(feature: dict, tolerance: float, precision: int = 5) -> dict:
    geom = make_valid(shape(feature["geometry"])).simplify(tolerance, preserve_topology=True)
    geometry = mapping(geom)
    geometry["coordinates"] = round_coords(geometry["coordinates"], precision)
    return {"type": "Feature", "properties": feature.get("properties") or {}, "geometry": geometry}


def write_geojson(path: Path, geojson: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(geojson, separators=(",", ":")), encoding="utf-8")


def load_geojson(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def lsoa_points_from_geojson(geojson: dict) -> dict[str, Point]:
    points = {}
    for feature in geojson.get("features", []):
        props = feature.get("properties") or {}
        area_id = str(props.get("area_id") or props.get("LSOA21CD") or "")
        lon = props.get("LONG")
        lat = props.get("LAT")
        if area_id and lon is not None and lat is not None:
            points[area_id] = Point(float(lon), float(lat))
    return points


def dz_points_from_coverage(coverage: pd.DataFrame) -> dict[str, Point]:
    points = {}
    rows = coverage[(coverage["area_type"] == "Data Zone") & coverage["lon"].notna() & coverage["lat"].notna()]
    for row in rows.itertuples(index=False):
        points[str(row.area_id)] = Point(float(row.lon), float(row.lat))
    return points


def build_parent_lookup(parent_geojson: dict, child_points: dict[str, Point]) -> pd.DataFrame:
    parent_records = []
    geometries = []
    for feature in parent_geojson.get("features", []):
        props = feature.get("properties") or {}
        geom = make_valid(shape(feature["geometry"]))
        geometries.append(geom)
        parent_records.append(
            {
                "parent_id": str(props.get("parent_id") or props.get("LAD24CD")),
                "parent_name": str(props.get("parent_name") or props.get("LAD24NM")),
            }
        )

    tree = STRtree(geometries)
    geom_id_to_index = {id(geom): index for index, geom in enumerate(geometries)}
    rows = []
    for area_id, point in child_points.items():
        parent_index = None
        for candidate in tree.query(point):
            # Shapely 2 may return geometry objects; keep this tolerant.
            index = int(candidate) if isinstance(candidate, numbers.Integral) else geom_id_to_index[id(candidate)]
            geom = geometries[index]
            if geom.contains(point) or geom.touches(point):
                parent_index = index
                break
        if parent_index is not None:
            rows.append({"area_id": area_id, **parent_records[parent_index]})
    return pd.DataFrame(rows)


def attach_parent_to_child_features(geojson: dict, lookup: pd.DataFrame) -> dict[str, list[dict]]:
    parent_by_area = lookup.set_index("area_id")[["parent_id", "parent_name"]].to_dict("index")
    by_parent: dict[str, list[dict]] = {}
    for feature in geojson.get("features", []):
        props = feature.setdefault("properties", {})
        area_id = str(props.get("area_id") or props.get("LSOA21CD") or props.get("DZCode") or "")
        parent = parent_by_area.get(area_id)
        if not parent:
            continue
        props["area_id"] = area_id
        props["parent_id"] = parent["parent_id"]
        props["parent_name"] = parent["parent_name"]
        by_parent.setdefault(parent["parent_id"], []).append(feature)
    return by_parent


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build parent LAD overview and per-parent child GeoJSON caches.")
    parser.add_argument("--child-tolerance", type=float, default=0.00012, help="Light simplification for drilldown child polygons.")
    parser.add_argument("--parent-tolerance", type=float, default=0.0012, help="Simplification for overview LAD polygons.")
    args = parser.parse_args()

    if PARENT_RAW.exists():
        parent_geojson = load_geojson(PARENT_RAW)
        print(f"Using existing {PARENT_RAW}")
    else:
        parent_geojson = fetch_lad_boundaries()
        write_geojson(PARENT_RAW, parent_geojson)
        print(f"Wrote {PARENT_RAW}")

    parent_simplified = {
        "type": "FeatureCollection",
        "features": [simplify_feature(feature, args.parent_tolerance) for feature in parent_geojson.get("features", [])],
    }
    write_geojson(PARENT_SIMPLIFIED, parent_simplified)
    print(f"Wrote {PARENT_SIMPLIFIED} ({PARENT_SIMPLIFIED.stat().st_size/1024/1024:.1f} MB)")

    coverage_path = Path(settings.area_coverage_file)
    if not coverage_path.is_absolute():
        coverage_path = ROOT / coverage_path
    coverage = read_frame(str(coverage_path))
    coverage["area_id"] = coverage["area_id"].astype(str)

    lsoa_geojson = load_geojson(BOUNDARY_DIR / "ew_lsoa_2021_bgc_v5.geojson")
    dz_geojson = load_geojson(BOUNDARY_DIR / "scotland_datazone_2022.geojson")
    child_points = {}
    child_points.update(lsoa_points_from_geojson(lsoa_geojson))
    child_points.update(dz_points_from_coverage(coverage))
    lookup = build_parent_lookup(parent_geojson, child_points)
    lookup.to_parquet(PARENT_LOOKUP, index=False)
    print(f"Wrote {PARENT_LOOKUP}: {len(lookup):,} area-parent rows")

    parent_coverage = (
        coverage.merge(lookup, on="area_id", how="left")
        .dropna(subset=["parent_id"])
        .groupby(["parent_id", "parent_name"], as_index=False)
        .agg(
            child_area_count=("area_id", "nunique"),
            median_deliverable_restaurant_count=("deliverable_restaurant_count", "median"),
            mean_deliverable_restaurant_count=("deliverable_restaurant_count", "mean"),
            min_deliverable_restaurant_count=("deliverable_restaurant_count", "min"),
            max_deliverable_restaurant_count=("deliverable_restaurant_count", "max"),
            food_restaurant_count=("food_restaurant_count", "sum"),
            fast_food_restaurant_count=("fast_food_restaurant_count", "sum"),
            median_food_restaurant_count=("food_restaurant_count", "median"),
            mean_food_restaurant_count=("food_restaurant_count", "mean"),
            median_fast_food_restaurant_count=("fast_food_restaurant_count", "median"),
            mean_fast_food_restaurant_count=("fast_food_restaurant_count", "mean"),
            median_fast_food_restaurant_share=("fast_food_restaurant_share", "median"),
            mean_fast_food_restaurant_share=("fast_food_restaurant_share", "mean"),
            coverage_label=("coverage_label", "first"),
        )
    )
    parent_coverage["fast_food_restaurant_share"] = (
        parent_coverage["fast_food_restaurant_count"] / parent_coverage["food_restaurant_count"]
    ).where(parent_coverage["food_restaurant_count"] > 0)
    parent_coverage.to_parquet(PARENT_COVERAGE, index=False)
    print(f"Wrote {PARENT_COVERAGE}: {len(parent_coverage):,} parent rows")

    CHILD_DIR.mkdir(parents=True, exist_ok=True)
    for old in CHILD_DIR.glob("*.geojson"):
        old.unlink()

    combined_child = {"type": "FeatureCollection", "features": lsoa_geojson.get("features", []) + dz_geojson.get("features", [])}
    by_parent = attach_parent_to_child_features(combined_child, lookup)
    total_size = 0
    for parent_id, features in by_parent.items():
        child_geojson = {
            "type": "FeatureCollection",
            "features": [simplify_feature(feature, args.child_tolerance) for feature in features],
        }
        path = CHILD_DIR / f"{safe_name(parent_id)}.geojson"
        write_geojson(path, child_geojson)
        total_size += path.stat().st_size
    print(f"Wrote {len(by_parent):,} child tile files ({total_size/1024/1024:.1f} MB total)")


if __name__ == "__main__":
    main()

