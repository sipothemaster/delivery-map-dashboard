from __future__ import annotations

import argparse
import json
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.validation import make_valid


DEFAULT_FILES = [
    (
        Path("data/boundaries/ew_lsoa_2021_bgc_v5.geojson"),
        Path("data/boundaries/ew_lsoa_2021_bgc_v5_simplified.geojson"),
        0.00035,
    ),
    (
        Path("data/boundaries/scotland_datazone_2022.geojson"),
        Path("data/boundaries/scotland_datazone_2022_simplified.geojson"),
        0.00045,
    ),
]


def round_coords(obj, ndigits: int = 5):
    if isinstance(obj, tuple):
        return tuple(round_coords(list(obj), ndigits))
    if isinstance(obj, list):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(obj[0]), ndigits), round(float(obj[1]), ndigits)]
        return [round_coords(item, ndigits) for item in obj]
    return obj


def count_points(obj) -> int:
    if isinstance(obj, list):
        if obj and isinstance(obj[0], (int, float)):
            return 1
        return sum(count_points(item) for item in obj)
    return 0


def simplify_geojson(input_path: Path, output_path: Path, tolerance: float, precision: int) -> None:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    output_features = []
    before_points = 0
    after_points = 0
    for feature in data.get("features", []):
        geometry = feature.get("geometry")
        if not geometry:
            continue
        before_points += count_points(geometry.get("coordinates"))
        geom = make_valid(shape(geometry))
        simplified = geom.simplify(tolerance, preserve_topology=True)
        simplified_geometry = mapping(simplified)
        simplified_geometry["coordinates"] = round_coords(simplified_geometry["coordinates"], precision)
        after_points += count_points(simplified_geometry.get("coordinates"))
        output_features.append(
            {
                "type": "Feature",
                "properties": feature.get("properties") or {},
                "geometry": simplified_geometry,
            }
        )
    output = {"type": "FeatureCollection", "features": output_features}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, separators=(",", ":")), encoding="utf-8")
    print(
        f"{input_path.name}: {len(output_features):,} features | "
        f"points {before_points:,} -> {after_points:,} | "
        f"size {input_path.stat().st_size/1024/1024:.1f} MB -> {output_path.stat().st_size/1024/1024:.1f} MB"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simplify dashboard boundary GeoJSON files for faster browser rendering.")
    parser.add_argument("--precision", type=int, default=5, help="Coordinate decimal places to keep.")
    parser.add_argument("--ew-tolerance", type=float, default=0.00035)
    parser.add_argument("--scotland-tolerance", type=float, default=0.00045)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    files = [
        (DEFAULT_FILES[0][0], DEFAULT_FILES[0][1], args.ew_tolerance),
        (DEFAULT_FILES[1][0], DEFAULT_FILES[1][1], args.scotland_tolerance),
    ]
    for input_path, output_path, tolerance in files:
        simplify_geojson(input_path, output_path, tolerance, args.precision)


if __name__ == "__main__":
    main()
