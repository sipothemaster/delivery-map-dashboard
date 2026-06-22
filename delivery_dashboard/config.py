from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


DEFAULT_INPUT_DIR = Path(r"C:\Users\sipoX\Documents\DFRE\code\WebscrapingDeliveryAvailability\data\input")


@dataclass(frozen=True)
class Settings:
    input_dir: Path = Path(os.getenv("DFRE_INPUT_DIR", DEFAULT_INPUT_DIR))
    ew_lsoa_workbook: Path = Path(
        os.getenv(
            "EW_LSOA_WORKBOOK",
            DEFAULT_INPUT_DIR / "England and Wales - one postcode per LSOA.xlsx",
        )
    )
    scotland_dz_workbook: Path = Path(
        os.getenv(
            "SCOTLAND_DZ_WORKBOOK",
            DEFAULT_INPUT_DIR / "AllDZ_OnePostcodePerDZ_RUC_SeeNotesTab.xlsx",
        )
    )
    ew_lsoa_centroids_file: str = os.getenv("EW_LSOA_CENTROIDS_FILE", "").strip()
    ew_lsoa_geojson_file: str = os.getenv("EW_LSOA_GEOJSON_FILE", "").strip()
    scotland_dz_geojson_file: str = os.getenv("SCOTLAND_DZ_GEOJSON_FILE", "").strip()
    delivery_map_file: str = os.getenv("DELIVERY_MAP_FILE", "").strip()
    restaurant_profile_file: str = os.getenv("RESTAURANT_PROFILE_FILE", "").strip()
    bq_project_id: str = os.getenv("BQ_PROJECT_ID", "delivery-availability-research")
    bq_dataset_id: str = os.getenv("BQ_DATASET_ID", "delivery_availability")
    bq_delivery_map_table: str = os.getenv("BQ_DELIVERY_MAP_TABLE", "postcode_restaurant_delivery_map")
    bq_restaurant_profile_table: str = os.getenv("BQ_RESTAURANT_PROFILE_TABLE", "restaurant_profile")
    bq_area_mapping_table: str = os.getenv("BQ_AREA_MAPPING_TABLE", "area_representative_postcodes")
    bq_area_coverage_table: str = os.getenv("BQ_AREA_COVERAGE_TABLE", "area_delivery_coverage")
    area_coverage_file: str = os.getenv("AREA_COVERAGE_FILE", "data/cache/area_delivery_coverage.parquet").strip()
    coverage_label: str = os.getenv("COVERAGE_LABEL", "weekday_full_20260520").strip()
    bq_max_rows: int = int(os.getenv("BQ_MAX_ROWS", "0") or "0")
    use_demo_data: bool = os.getenv("USE_DEMO_DATA", "true").lower() in {"1", "true", "yes", "y"}
    dash_host: str = os.getenv("DASH_HOST", "127.0.0.1")
    dash_port: int = int(os.getenv("DASH_PORT", "8050"))


settings = Settings()



