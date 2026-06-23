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
from delivery_dashboard.data import read_frame


DAY_ORDER = [
    ("Monday", 1),
    ("Tuesday", 2),
    ("Wednesday", 3),
    ("Thursday", 4),
    ("Friday", 5),
    ("Saturday", 6),
    ("Sunday", 7),
]


def table_id(table_name: str) -> str:
    if table_name.count(".") == 2:
        return table_name
    return f"{settings.bq_project_id}.{settings.bq_dataset_id}.{table_name}"


def build_area_opening_coverage_table(
    client: bigquery.Client,
    coverage_label: str | None,
    destination_table: str,
    opening_table: str,
) -> None:
    mapping = table_id(settings.bq_area_mapping_table)
    delivery_map = table_id(settings.bq_delivery_map_table)
    area_coverage = table_id(settings.bq_area_coverage_table)
    opening = table_id(opening_table)
    destination = table_id(destination_table)

    delivery_where_sql = "WHERE CAST(is_delivery AS BOOL)"
    query_params = []
    if coverage_label:
        delivery_where_sql = "WHERE snapshot_label = @coverage_label AND CAST(is_delivery AS BOOL)"
        query_params.append(bigquery.ScalarQueryParameter("coverage_label", "STRING", coverage_label))

    query = f"""
    CREATE OR REPLACE TABLE `{destination}` AS
    WITH latest_run AS (
      SELECT run_id
      FROM (
        SELECT
          run_id,
          COUNT(DISTINCT restaurant_id) AS restaurant_count,
          MAX(fetched_at) AS max_fetched_at
        FROM `{opening}`
        WHERE service_type = 'delivery'
        GROUP BY run_id
      )
      ORDER BY restaurant_count DESC, max_fetched_at DESC
      LIMIT 1
    ),
    days AS (
      SELECT 'Monday' AS day_of_week, 1 AS day_index UNION ALL
      SELECT 'Tuesday', 2 UNION ALL
      SELECT 'Wednesday', 3 UNION ALL
      SELECT 'Thursday', 4 UNION ALL
      SELECT 'Friday', 5 UNION ALL
      SELECT 'Saturday', 6 UNION ALL
      SELECT 'Sunday', 7
    ),
    hours AS (
      SELECT hour_of_day
      FROM UNNEST(GENERATE_ARRAY(0, 23)) AS hour_of_day
    ),
    area_hours AS (
      SELECT
        a.area_id,
        a.area_type,
        a.area_name,
        a.representative_postcode,
        a.representative_postcode_clean,
        a.lon,
        a.lat,
        d.day_of_week,
        d.day_index,
        h.hour_of_day
      FROM `{mapping}` AS a
      CROSS JOIN days AS d
      CROSS JOIN hours AS h
    ),
    deliverable_map AS (
      SELECT DISTINCT
        LOWER(REGEXP_REPLACE(CAST(postcode AS STRING), r'\\s+', '')) AS postcode_clean,
        CAST(restaurant_id AS STRING) AS restaurant_id
      FROM `{delivery_map}`
      {delivery_where_sql}
    ),
    deliverable_area_restaurants AS (
      SELECT DISTINCT
        a.area_id,
        m.restaurant_id
      FROM `{mapping}` AS a
      JOIN deliverable_map AS m
        ON a.representative_postcode_clean = m.postcode_clean
    ),
    opening_intervals AS (
      SELECT
        CAST(restaurant_id AS STRING) AS restaurant_id,
        day_of_week,
        CASE day_of_week
          WHEN 'Monday' THEN 1
          WHEN 'Tuesday' THEN 2
          WHEN 'Wednesday' THEN 3
          WHEN 'Thursday' THEN 4
          WHEN 'Friday' THEN 5
          WHEN 'Saturday' THEN 6
          WHEN 'Sunday' THEN 7
        END AS day_index,
        SAFE_CAST(SPLIT(opens_at_local, ':')[OFFSET(0)] AS INT64) * 60
          + SAFE_CAST(SPLIT(opens_at_local, ':')[OFFSET(1)] AS INT64) AS opens_minute,
        SAFE_CAST(SPLIT(closes_at_local, ':')[OFFSET(0)] AS INT64) * 60
          + SAFE_CAST(SPLIT(closes_at_local, ':')[OFFSET(1)] AS INT64) AS closes_minute,
        COALESCE(crosses_midnight, FALSE) AS crosses_midnight
      FROM `{opening}`
      WHERE run_id = (SELECT run_id FROM latest_run)
        AND service_type = 'delivery'
        AND opens_at_local IS NOT NULL
        AND closes_at_local IS NOT NULL
        AND day_of_week IS NOT NULL
    ),
    open_hours AS (
      SELECT DISTINCT
        restaurant_id,
        day_of_week,
        day_index,
        hour_of_day
      FROM opening_intervals
      JOIN hours
        ON NOT crosses_midnight
       AND hour_of_day * 60 >= opens_minute
       AND hour_of_day * 60 < closes_minute

      UNION DISTINCT

      SELECT DISTINCT
        restaurant_id,
        day_of_week,
        day_index,
        hour_of_day
      FROM opening_intervals
      JOIN hours
        ON crosses_midnight
       AND hour_of_day * 60 >= opens_minute

      UNION DISTINCT

      SELECT DISTINCT
        restaurant_id,
        CASE day_index
          WHEN 1 THEN 'Tuesday'
          WHEN 2 THEN 'Wednesday'
          WHEN 3 THEN 'Thursday'
          WHEN 4 THEN 'Friday'
          WHEN 5 THEN 'Saturday'
          WHEN 6 THEN 'Sunday'
          WHEN 7 THEN 'Monday'
        END AS day_of_week,
        CASE day_index WHEN 7 THEN 1 ELSE day_index + 1 END AS day_index,
        hour_of_day
      FROM opening_intervals
      JOIN hours
        ON crosses_midnight
       AND hour_of_day * 60 < closes_minute
    ),
    open_area_hours AS (
      SELECT
        dar.area_id,
        oh.day_of_week,
        oh.day_index,
        oh.hour_of_day,
        COUNT(DISTINCT dar.restaurant_id) AS open_restaurant_count
      FROM deliverable_area_restaurants AS dar
      JOIN open_hours AS oh
        ON dar.restaurant_id = oh.restaurant_id
      GROUP BY
        dar.area_id,
        oh.day_of_week,
        oh.day_index,
        oh.hour_of_day
    )
    SELECT
      ah.area_id,
      ah.area_type,
      ah.area_name,
      ah.representative_postcode,
      ah.representative_postcode_clean,
      ah.lon,
      ah.lat,
      ah.day_of_week,
      ah.day_index,
      ah.hour_of_day,
      COALESCE(ac.deliverable_restaurant_count, 0) AS deliverable_restaurant_count,
      COALESCE(oah.open_restaurant_count, 0) AS open_restaurant_count,
      SAFE_DIVIDE(COALESCE(oah.open_restaurant_count, 0), ac.deliverable_restaurant_count) AS open_restaurant_share,
      (SELECT run_id FROM latest_run) AS opening_run_id,
      CURRENT_TIMESTAMP() AS updated_at
    FROM area_hours AS ah
    LEFT JOIN `{area_coverage}` AS ac
      ON ah.area_id = ac.area_id
    LEFT JOIN open_area_hours AS oah
      ON ah.area_id = oah.area_id
     AND ah.day_of_week = oah.day_of_week
     AND ah.hour_of_day = oah.hour_of_day
    """
    job_config = bigquery.QueryJobConfig(query_parameters=query_params)
    client.query(query, job_config=job_config).result()
    print(f"Built {destination}")


def download_hourly_caches(
    client: bigquery.Client,
    source_table: str,
    output_dir: str,
) -> None:
    source = table_id(source_table)
    out = Path(output_dir)
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)

    for day_name, day_index in DAY_ORDER:
        for hour in range(24):
            query = f"""
            SELECT
              area_id,
              day_of_week,
              day_index,
              hour_of_day,
              open_restaurant_count,
              open_restaurant_share,
              opening_run_id
            FROM `{source}`
            WHERE day_index = @day_index
              AND hour_of_day = @hour
            """
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("day_index", "INT64", day_index),
                    bigquery.ScalarQueryParameter("hour", "INT64", hour),
                ]
            )
            df = client.query(query, job_config=job_config).to_dataframe()
            path = out / f"{day_name}_{hour:02d}.parquet"
            df.to_parquet(path, index=False)
            print(f"Wrote {path}: {len(df):,} rows")


def build_parent_hourly_caches(area_dir: str, parent_dir: str) -> None:
    area_path = Path(area_dir)
    parent_path = Path(parent_dir)
    if not area_path.is_absolute():
        area_path = ROOT / area_path
    if not parent_path.is_absolute():
        parent_path = ROOT / parent_path
    parent_path.mkdir(parents=True, exist_ok=True)

    lookup = read_frame(str(ROOT / "data/cache/area_parent_lookup.parquet"))
    coverage = read_frame(str(ROOT / settings.area_coverage_file))[["area_id", "deliverable_restaurant_count"]]
    lookup["area_id"] = lookup["area_id"].astype(str)
    coverage["area_id"] = coverage["area_id"].astype(str)

    for file in sorted(area_path.glob("*.parquet")):
        df = read_frame(str(file))
        df["area_id"] = df["area_id"].astype(str)
        joined = df.merge(lookup, on="area_id", how="left").merge(coverage, on="area_id", how="left")
        parent = (
            joined.dropna(subset=["parent_id"])
            .groupby(["parent_id", "parent_name"], as_index=False)
            .agg(
                open_restaurant_count=("open_restaurant_count", "sum"),
                deliverable_restaurant_count=("deliverable_restaurant_count", "sum"),
                median_open_restaurant_count=("open_restaurant_count", "median"),
                median_open_restaurant_share=("open_restaurant_share", "median"),
                opening_run_id=("opening_run_id", "first"),
            )
        )
        parent["open_restaurant_share"] = (
            parent["open_restaurant_count"] / parent["deliverable_restaurant_count"]
        ).where(parent["deliverable_restaurant_count"] > 0)
        output = parent_path / file.name
        parent.to_parquet(output, index=False)
        print(f"Wrote {output}: {len(parent):,} rows")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build hourly opening coverage caches for the delivery map.")
    parser.add_argument("--build-table", action="store_true")
    parser.add_argument("--download-cache", action="store_true")
    parser.add_argument("--build-parent-cache", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--coverage-label", default=settings.coverage_label or None)
    parser.add_argument("--destination-table", default="area_opening_coverage")
    parser.add_argument("--opening-table", default="restaurant_opening_times")
    parser.add_argument("--area-output-dir", default="data/cache/opening_by_hour")
    parser.add_argument("--parent-output-dir", default="data/cache/parent_opening_by_hour")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not (args.all or args.build_table or args.download_cache or args.build_parent_cache):
        args.all = True
    client = bigquery.Client(project=settings.bq_project_id, location="europe-west2")
    if args.all or args.build_table:
        build_area_opening_coverage_table(
            client,
            args.coverage_label,
            args.destination_table,
            args.opening_table,
        )
    if args.all or args.download_cache:
        download_hourly_caches(client, args.destination_table, args.area_output_dir)
    if args.all or args.build_parent_cache:
        build_parent_hourly_caches(args.area_output_dir, args.parent_output_dir)


if __name__ == "__main__":
    main()
