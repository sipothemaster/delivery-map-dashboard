from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

from delivery_dashboard.config import settings


CORE_DELIVERY_COLUMNS = [
    "snapshot_label",
    "postcode",
    "restaurant_id",
    "is_delivery",
    "delivery_fee",
    "minimum_delivery_value",
    "delivery_eta_lower_minutes",
    "delivery_eta_upper_minutes",
    "drive_distance_meters",
]

CORE_PROFILE_COLUMNS = [
    "restaurant_id",
    "restaurant_name",
    "restaurant_unique_name",
    "restaurant_url",
    "cuisine_names",
    "rating_count",
    "rating_star",
    "latitude",
    "longitude",
]


def clean_postcode(value: object) -> str:
    return "".join(str(value or "").lower().split())


def read_frame(path_text: str) -> pd.DataFrame:
    path = Path(path_text)
    if not path.exists():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"Unsupported file type: {path}")


def load_ew_lsoa_lookup() -> pd.DataFrame:
    df = pd.read_excel(settings.ew_lsoa_workbook, sheet_name=0, dtype=str)
    df = df.rename(columns={"LSOA21CD": "area_id", "POSTCODE": "representative_postcode"})
    df = df[["area_id", "representative_postcode"]].copy()
    df["area_type"] = "LSOA"
    df["area_name"] = df["area_id"]
    df["lon"] = pd.NA
    df["lat"] = pd.NA

    if settings.ew_lsoa_centroids_file:
        centroids = read_frame(settings.ew_lsoa_centroids_file)
        expected = {"area_id", "lon", "lat"}
        missing = expected - set(centroids.columns)
        if missing:
            raise ValueError(
                "EW_LSOA_CENTROIDS_FILE must contain columns: " + ", ".join(sorted(expected))
            )
        keep = ["area_id", "lon", "lat"]
        if "area_name" in centroids.columns:
            keep.append("area_name")
        df = df.drop(columns=["lon", "lat", "area_name"]).merge(
            centroids[keep], on="area_id", how="left"
        )
        if "area_name" not in df.columns:
            df["area_name"] = df["area_id"]

    return df


def load_scotland_dz_lookup() -> pd.DataFrame:
    df = pd.read_excel(settings.scotland_dz_workbook, sheet_name="Sheet1")
    df = df.rename(
        columns={
            "DZCode": "area_id",
            "DZName": "area_name",
            "Postcode": "representative_postcode",
            "Lon": "lon",
            "Lat": "lat",
            "UR8Name": "urban_rural_8",
            "UR6Name": "urban_rural_6",
            "UR3Name": "urban_rural_3",
            "UR2Name": "urban_rural_2",
        }
    )
    keep = [
        "area_id",
        "area_name",
        "representative_postcode",
        "lon",
        "lat",
        "urban_rural_8",
        "urban_rural_6",
        "urban_rural_3",
        "urban_rural_2",
    ]
    df = df[[col for col in keep if col in df.columns]].copy()
    df["area_type"] = "Data Zone"
    return df


def load_area_lookup() -> pd.DataFrame:
    areas = pd.concat([load_ew_lsoa_lookup(), load_scotland_dz_lookup()], ignore_index=True)
    areas["representative_postcode_clean"] = areas["representative_postcode"].map(clean_postcode)
    areas["lon"] = pd.to_numeric(areas["lon"], errors="coerce")
    areas["lat"] = pd.to_numeric(areas["lat"], errors="coerce")
    return areas


def query_bigquery_table(table_name: str, columns: list[str]) -> pd.DataFrame:
    table_id = f"{settings.bq_project_id}.{settings.bq_dataset_id}.{table_name}"
    limit_sql = f"LIMIT {settings.bq_max_rows}" if settings.bq_max_rows > 0 else ""
    col_sql = ", ".join(f"`{col}`" for col in columns)
    query = f"SELECT {col_sql} FROM `{table_id}` {limit_sql}"
    client = bigquery.Client(project=settings.bq_project_id)
    return client.query(query).to_dataframe()


def load_delivery_map() -> pd.DataFrame:
    if settings.delivery_map_file:
        return read_frame(settings.delivery_map_file)
    return query_bigquery_table(settings.bq_delivery_map_table, CORE_DELIVERY_COLUMNS)


def load_restaurant_profile() -> pd.DataFrame:
    if settings.restaurant_profile_file:
        return read_frame(settings.restaurant_profile_file)
    return query_bigquery_table(settings.bq_restaurant_profile_table, CORE_PROFILE_COLUMNS)


def build_demo_data(area_lookup: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    scotland = area_lookup.dropna(subset=["lon", "lat"]).head(8).copy()
    if scotland.empty:
        scotland = area_lookup.head(8).copy()
        scotland["lon"] = [-2.27, -2.18, -3.19, -4.25, -3.53, -2.99, -4.14, -3.92][: len(scotland)]
        scotland["lat"] = [57.10, 57.15, 55.95, 55.86, 55.91, 56.46, 57.48, 56.12][: len(scotland)]

    restaurants = [
        ("1001", "Everyday Sushi", "Japanese, Sushi", 4.6, 210),
        ("1002", "Green Bowl Kitchen", "Healthy, Salads", 4.4, 98),
        ("1003", "Pizza North", "Pizza, Italian", 4.1, 640),
        ("1004", "Spice Junction", "Indian, Curry", 4.3, 380),
        ("1005", "Burger Yard", "Burgers, American", 4.0, 520),
        ("1006", "Noodle House", "Chinese, Noodles", 4.2, 255),
    ]
    profile_rows = []
    for rid, name, cuisines, rating, count in restaurants:
        profile_rows.append(
            {
                "restaurant_id": rid,
                "restaurant_name": name,
                "restaurant_unique_name": name.lower().replace(" ", "-"),
                "restaurant_url": f"https://www.just-eat.co.uk/restaurants-{name.lower().replace(' ', '-')}/menu",
                "cuisine_names": cuisines,
                "rating_star": rating,
                "rating_count": count,
                "latitude": math.nan,
                "longitude": math.nan,
            }
        )

    delivery_rows = []
    for area_index, area in scotland.reset_index(drop=True).iterrows():
        postcode = area["representative_postcode_clean"]
        restaurant_count = 2 + (area_index % len(restaurants))
        for rest_index, restaurant in enumerate(restaurants[:restaurant_count]):
            rid = restaurant[0]
            delivery_rows.append(
                {
                    "snapshot_label": "demo",
                    "postcode": postcode,
                    "restaurant_id": rid,
                    "is_delivery": rest_index % 5 != 4,
                    "delivery_fee": round((rest_index % 4) * 0.99, 2),
                    "minimum_delivery_value": [0, 8, 10, 12, 15, 20][rest_index % 6],
                    "delivery_eta_lower_minutes": 15 + rest_index * 5 + area_index,
                    "delivery_eta_upper_minutes": 25 + rest_index * 6 + area_index,
                    "drive_distance_meters": 600 + rest_index * 450 + area_index * 120,
                }
            )
    return pd.DataFrame(delivery_rows), pd.DataFrame(profile_rows)


def load_all_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    area_lookup = load_area_lookup()
    has_local_data = bool(settings.delivery_map_file and settings.restaurant_profile_file)
    if settings.use_demo_data and not has_local_data:
        delivery, profile = build_demo_data(area_lookup)
        return area_lookup, delivery, profile, "demo"

    try:
        delivery = load_delivery_map()
        profile = load_restaurant_profile()
        mode = "local" if has_local_data else "bigquery"
    except Exception as exc:
        if not settings.use_demo_data:
            raise
        delivery, profile = build_demo_data(area_lookup)
        mode = f"demo ({exc.__class__.__name__}: {exc})"
    return area_lookup, delivery, profile, mode


AREA_COVERAGE_COLUMNS = [
    "area_id",
    "area_type",
    "area_name",
    "representative_postcode",
    "representative_postcode_clean",
    "deliverable_restaurant_count",
    "coverage_label",
    "updated_at",
]


def load_area_coverage_file() -> pd.DataFrame:
    path_text = settings.area_coverage_file
    if not path_text:
        raise FileNotFoundError("AREA_COVERAGE_FILE is not configured")
    path = Path(path_text)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        raise FileNotFoundError(path)
    return read_frame(str(path))


def query_area_coverage_table() -> pd.DataFrame:
    table_id = f"{settings.bq_project_id}.{settings.bq_dataset_id}.{settings.bq_area_coverage_table}"
    query = f"SELECT * FROM `{table_id}`"
    client = bigquery.Client(project=settings.bq_project_id)
    return client.query(query).to_dataframe()


def load_area_coverage_for_dashboard() -> tuple[pd.DataFrame, str]:
    try:
        df = load_area_coverage_file()
        mode = "area coverage cache"
    except Exception as cache_exc:
        if settings.use_demo_data:
            area_lookup = load_area_lookup()
            delivery, profile = build_demo_data(area_lookup)
            from delivery_dashboard.metrics import compute_area_metrics, prepare_joined_data

            joined = prepare_joined_data(area_lookup, delivery, profile)
            metrics = compute_area_metrics(joined)
            metrics = metrics.rename(
                columns={"delivery_restaurant_count": "deliverable_restaurant_count"}
            )
            metrics["coverage_label"] = "demo"
            metrics["updated_at"] = pd.Timestamp.utcnow()
            return metrics, "demo"
        try:
            df = query_area_coverage_table()
            mode = "BigQuery area coverage"
        except Exception as bq_exc:
            raise RuntimeError(
                f"Could not load area coverage cache ({cache_exc}) or BigQuery coverage table ({bq_exc})"
            ) from bq_exc

    if "delivery_restaurant_count" in df.columns and "deliverable_restaurant_count" not in df.columns:
        df = df.rename(columns={"delivery_restaurant_count": "deliverable_restaurant_count"})
    df["area_id"] = df["area_id"].astype(str)
    df["deliverable_restaurant_count"] = pd.to_numeric(
        df["deliverable_restaurant_count"], errors="coerce"
    ).fillna(0)
    return df, mode

