from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
from google.cloud import bigquery

from delivery_dashboard.config import settings
from delivery_dashboard.data import load_area_lookup


AREA_MAPPING_SCHEMA = [
    bigquery.SchemaField("area_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("area_type", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("area_name", "STRING"),
    bigquery.SchemaField("representative_postcode", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("representative_postcode_clean", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("lon", "FLOAT"),
    bigquery.SchemaField("lat", "FLOAT"),
    bigquery.SchemaField("urban_rural_8", "STRING"),
    bigquery.SchemaField("urban_rural_6", "STRING"),
    bigquery.SchemaField("urban_rural_3", "STRING"),
    bigquery.SchemaField("urban_rural_2", "STRING"),
]


def table_id(table_name: str) -> str:
    if table_name.count(".") == 2:
        return table_name
    return f"{settings.bq_project_id}.{settings.bq_dataset_id}.{table_name}"


def ensure_dataset(client: bigquery.Client) -> None:
    dataset = bigquery.Dataset(f"{settings.bq_project_id}.{settings.bq_dataset_id}")
    dataset.location = "europe-west2"
    client.create_dataset(dataset, exists_ok=True)


def area_mapping_frame() -> pd.DataFrame:
    areas = load_area_lookup().copy()
    for col in ["urban_rural_8", "urban_rural_6", "urban_rural_3", "urban_rural_2"]:
        if col not in areas.columns:
            areas[col] = pd.NA
    keep = [field.name for field in AREA_MAPPING_SCHEMA]
    areas = areas[keep]
    areas["area_id"] = areas["area_id"].astype(str)
    areas["representative_postcode_clean"] = areas["representative_postcode_clean"].astype(str)
    return areas


def upload_area_mapping(client: bigquery.Client) -> None:
    df = area_mapping_frame()
    destination = table_id(settings.bq_area_mapping_table)
    job_config = bigquery.LoadJobConfig(
        schema=AREA_MAPPING_SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    client.load_table_from_dataframe(df, destination, job_config=job_config).result()
    print(f"Uploaded {len(df):,} rows to {destination}")


def build_area_coverage_table(client: bigquery.Client, coverage_label: str | None) -> None:
    mapping = table_id(settings.bq_area_mapping_table)
    source = table_id(settings.bq_delivery_map_table)
    destination = table_id(settings.bq_area_coverage_table)

    where_sql = ""
    query_params = []
    coverage_expr = "CAST(NULL AS STRING)"
    if coverage_label:
        # This is a static coverage-version label from postcode_restaurant_delivery_map, not an open-now snapshot table.
        where_sql = "WHERE snapshot_label = @coverage_label"
        query_params.append(bigquery.ScalarQueryParameter("coverage_label", "STRING", coverage_label))
        coverage_expr = "@coverage_label"

    query = f"""
    CREATE OR REPLACE TABLE `{destination}` AS
    WITH source_map AS (
      SELECT
        LOWER(REGEXP_REPLACE(CAST(postcode AS STRING), r'\\s+', '')) AS postcode_clean,
        CAST(restaurant_id AS STRING) AS restaurant_id,
        CAST(is_delivery AS BOOL) AS is_delivery
      FROM `{source}`
      {where_sql}
    )
    SELECT
      a.area_id,
      a.area_type,
      a.area_name,
      a.representative_postcode,
      a.representative_postcode_clean,
      a.lon,
      a.lat,
      a.urban_rural_8,
      a.urban_rural_6,
      a.urban_rural_3,
      a.urban_rural_2,
      COUNT(DISTINCT IF(m.is_delivery, m.restaurant_id, NULL)) AS deliverable_restaurant_count,
      {coverage_expr} AS coverage_label,
      CURRENT_TIMESTAMP() AS updated_at
    FROM `{mapping}` AS a
    LEFT JOIN source_map AS m
      ON a.representative_postcode_clean = m.postcode_clean
    GROUP BY
      a.area_id,
      a.area_type,
      a.area_name,
      a.representative_postcode,
      a.representative_postcode_clean,
      a.lon,
      a.lat,
      a.urban_rural_8,
      a.urban_rural_6,
      a.urban_rural_3,
      a.urban_rural_2
    """
    job_config = bigquery.QueryJobConfig(query_parameters=query_params)
    client.query(query, job_config=job_config).result()
    print(f"Built {destination}")


def download_cache(client: bigquery.Client, output_path: str) -> None:
    destination = table_id(settings.bq_area_coverage_table)
    df = client.query(f"SELECT * FROM `{destination}`").to_dataframe()
    output = Path(output_path)
    if not output.is_absolute():
        output = Path.cwd() / output
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output, index=False)
    print(f"Downloaded {len(df):,} rows to {output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the lightweight DFRE static area delivery coverage table/cache.")
    parser.add_argument("--upload-mapping", action="store_true", help="Upload area_representative_postcodes to BigQuery.")
    parser.add_argument("--build-table", action="store_true", help="Create or replace area_delivery_coverage in BigQuery.")
    parser.add_argument("--download-cache", action="store_true", help="Download area_delivery_coverage to local parquet cache.")
    parser.add_argument("--all", action="store_true", help="Run upload mapping, build table, and download cache.")
    parser.add_argument("--coverage-label", default=settings.coverage_label or None)
    parser.add_argument("--output", default=settings.area_coverage_file)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not (args.all or args.upload_mapping or args.build_table or args.download_cache):
        args.all = True

    client = bigquery.Client(project=settings.bq_project_id, location="europe-west2")
    ensure_dataset(client)
    if args.all or args.upload_mapping:
        upload_area_mapping(client)
    if args.all or args.build_table:
        build_area_coverage_table(client, args.coverage_label)
    if args.all or args.download_cache:
        download_cache(client, args.output)


if __name__ == "__main__":
    main()
