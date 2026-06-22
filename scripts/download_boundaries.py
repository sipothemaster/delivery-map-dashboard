from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from zipfile import ZipFile

import shapefile
from pyproj import Transformer


BOUNDARY_DIR = Path("data/boundaries")

LSOA_SERVICE = {
    "name": "ew_lsoa_2021_bgc_v5",
    "url": "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/Lower_layer_Super_Output_Areas_December_2021_Boundaries_EW_BGC_V5/FeatureServer/0/query",
    "out_fields": "LSOA21CD,LSOA21NM,LAT,LONG",
    "id_field": "LSOA21CD",
    "output": BOUNDARY_DIR / "ew_lsoa_2021_bgc_v5.geojson",
}

SCOTLAND_ZIP_URL = "https://maps.gov.scot/ATOM/shapefiles/SG_DataZoneBdry_2022.zip"
SCOTLAND_ZIP_PATH = BOUNDARY_DIR / "SG_DataZoneBdry_2022.zip"
SCOTLAND_OUTPUT = BOUNDARY_DIR / "scotland_datazone_2022.geojson"


def request_json(url: str, params: dict) -> dict:
    full_url = f"{url}?{urlencode(params)}"
    with urlopen(full_url, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def count_features(service: dict) -> int:
    payload = request_json(service["url"], {"where": "1=1", "returnCountOnly": "true", "f": "json"})
    if "error" in payload:
        raise RuntimeError(payload["error"])
    return int(payload["count"])


def fetch_lsoa_page(service: dict, offset: int, page_size: int) -> list[dict]:
    payload = request_json(
        service["url"],
        {
            "where": "1=1",
            "outFields": service["out_fields"],
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": page_size,
        },
    )
    if "error" in payload:
        raise RuntimeError(payload["error"])
    features = payload.get("features") or []
    for feature in features:
        props = feature.setdefault("properties", {})
        if props.get("area_id") is None and props.get(service["id_field"]) is not None:
            props["area_id"] = str(props[service["id_field"]])
    return features


def download_lsoa(page_size: int = 2000) -> None:
    total = count_features(LSOA_SERVICE)
    print(f"{LSOA_SERVICE['name']}: {total:,} features")
    features = []
    for offset in range(0, total, page_size):
        page = fetch_lsoa_page(LSOA_SERVICE, offset, page_size)
        features.extend(page)
        print(f"  fetched {len(features):,}/{total:,}", flush=True)
        time.sleep(0.1)
    LSOA_SERVICE["output"].parent.mkdir(parents=True, exist_ok=True)
    with LSOA_SERVICE["output"].open("w", encoding="utf-8") as handle:
        json.dump({"type": "FeatureCollection", "features": features}, handle)
    print(f"  wrote {LSOA_SERVICE['output']}")


def download_file(url: str, output: Path) -> None:
    if output.exists() and output.stat().st_size > 0:
        print(f"using existing {output}")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {url}")
    with urlopen(url, timeout=180) as response, output.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    print(f"  wrote {output}")


def extract_shapefile(zip_path: Path, extract_dir: Path) -> Path:
    extract_dir.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)
    shp_files = sorted(extract_dir.rglob("*.shp"))
    if not shp_files:
        raise FileNotFoundError("No .shp file found in Scottish Data Zone zip")
    print("  shapefile:", shp_files[0])
    return shp_files[0]


def ring_area(ring: list[list[float]]) -> float:
    area = 0.0
    for index, point in enumerate(ring):
        x1, y1 = point
        x2, y2 = ring[(index + 1) % len(ring)]
        area += x1 * y2 - x2 * y1
    return area / 2.0


def orient_ring(ring: list[list[float]], clockwise: bool) -> list[list[float]]:
    is_clockwise = ring_area(ring) < 0
    if is_clockwise != clockwise:
        return list(reversed(ring))
    return ring


def shape_to_polygon(shape, transformer: Transformer) -> dict:
    points = [list(transformer.transform(x, y)) for x, y in shape.points]
    part_starts = list(shape.parts) + [len(points)]
    rings = []
    for start, end in zip(part_starts[:-1], part_starts[1:]):
        ring = points[start:end]
        if ring and ring[0] != ring[-1]:
            ring.append(ring[0])
        if len(ring) >= 4:
            rings.append(ring)
    if not rings:
        return {"type": "Polygon", "coordinates": []}
    outer = orient_ring(rings[0], clockwise=False)
    holes = [orient_ring(ring, clockwise=True) for ring in rings[1:]]
    return {"type": "Polygon", "coordinates": [outer, *holes]}


def convert_scotland_shapefile() -> None:
    download_file(SCOTLAND_ZIP_URL, SCOTLAND_ZIP_PATH)
    shp_path = extract_shapefile(SCOTLAND_ZIP_PATH, BOUNDARY_DIR / "scotland_datazone_2022_shp")
    reader = shapefile.Reader(str(shp_path), encoding="latin1")
    fields = [field[0] for field in reader.fields[1:]]
    transformer = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
    features = []
    for record, shape in zip(reader.records(), reader.shapes()):
        props = dict(zip(fields, record))
        dz_code = str(props.get("dzcode") or props.get("DZ_CODE") or props.get("DZCode") or props.get("DataZone") or "")
        dz_name = str(props.get("dzname") or props.get("DZ_NAME") or props.get("DZName") or "")
        if not dz_code:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "area_id": dz_code,
                    "DZCode": dz_code,
                    "DZName": dz_name,
                },
                "geometry": shape_to_polygon(shape, transformer),
            }
        )
    with SCOTLAND_OUTPUT.open("w", encoding="utf-8") as handle:
        json.dump({"type": "FeatureCollection", "features": features}, handle)
    print(f"scotland_datazone_2022: {len(features):,} features")
    print(f"  wrote {SCOTLAND_OUTPUT}")


def main() -> None:
    download_lsoa()
    convert_scotland_shapefile()


if __name__ == "__main__":
    main()

