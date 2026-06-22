from __future__ import annotations

import pandas as pd

from delivery_dashboard.data import clean_postcode


def split_cuisines(value: object) -> list[str]:
    if value is None or pd.isna(value):
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def prepare_joined_data(
    area_lookup: pd.DataFrame,
    delivery: pd.DataFrame,
    profile: pd.DataFrame,
) -> pd.DataFrame:
    delivery = delivery.copy()
    profile = profile.copy()
    delivery["postcode_clean"] = delivery["postcode"].map(clean_postcode)
    delivery["restaurant_id"] = delivery["restaurant_id"].astype(str)
    profile["restaurant_id"] = profile["restaurant_id"].astype(str)

    numeric_cols = [
        "delivery_fee",
        "minimum_delivery_value",
        "delivery_eta_lower_minutes",
        "delivery_eta_upper_minutes",
        "drive_distance_meters",
    ]
    for col in numeric_cols:
        if col in delivery.columns:
            delivery[col] = pd.to_numeric(delivery[col], errors="coerce")

    if "rating_star" in profile.columns:
        profile["rating_star"] = pd.to_numeric(profile["rating_star"], errors="coerce")

    joined = delivery.merge(profile, on="restaurant_id", how="left")
    joined = joined.merge(
        area_lookup,
        left_on="postcode_clean",
        right_on="representative_postcode_clean",
        how="left",
    )
    joined["is_delivery"] = joined["is_delivery"].fillna(False).astype(bool)
    joined["cuisine_list"] = joined["cuisine_names"].map(split_cuisines)
    return joined


def apply_filters(
    data: pd.DataFrame,
    area_type: str | None = None,
    cuisine: str | None = None,
    rating_min: float | None = None,
    fee_max: float | None = None,
    min_order_max: float | None = None,
    eta_max: float | None = None,
) -> pd.DataFrame:
    df = data.copy()
    if area_type and area_type != "All":
        df = df[df["area_type"] == area_type]
    if cuisine and cuisine != "All":
        df = df[df["cuisine_list"].map(lambda items: cuisine in items)]
    if rating_min is not None:
        df = df[df["rating_star"].isna() | (df["rating_star"] >= rating_min)]
    if fee_max is not None:
        df = df[df["delivery_fee"].isna() | (df["delivery_fee"] <= fee_max)]
    if min_order_max is not None:
        df = df[df["minimum_delivery_value"].isna() | (df["minimum_delivery_value"] <= min_order_max)]
    if eta_max is not None:
        df = df[df["delivery_eta_upper_minutes"].isna() | (df["delivery_eta_upper_minutes"] <= eta_max)]
    return df


def cuisine_summary(items: pd.Series, top_n: int = 3) -> str:
    exploded = [cuisine for row in items for cuisine in row]
    if not exploded:
        return ""
    counts = pd.Series(exploded).value_counts().head(top_n)
    return ", ".join(f"{name} ({count})" for name, count in counts.items())


def cuisine_diversity(items: pd.Series) -> int:
    return len({cuisine for row in items for cuisine in row})


def compute_area_metrics(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame()

    grouped = data.groupby(
        [
            "area_id",
            "area_name",
            "area_type",
            "representative_postcode",
            "lon",
            "lat",
        ],
        dropna=False,
    )
    metrics = grouped.agg(
        restaurant_count=("restaurant_id", "nunique"),
        delivery_restaurant_count=("restaurant_id", lambda s: data.loc[s.index].loc[data.loc[s.index, "is_delivery"], "restaurant_id"].nunique()),
        median_delivery_fee=("delivery_fee", "median"),
        median_minimum_order=("minimum_delivery_value", "median"),
        median_eta_lower=("delivery_eta_lower_minutes", "median"),
        median_eta_upper=("delivery_eta_upper_minutes", "median"),
        median_drive_distance_m=("drive_distance_meters", "median"),
        median_rating=("rating_star", "median"),
        cuisine_diversity=("cuisine_list", cuisine_diversity),
        top_cuisines=("cuisine_list", cuisine_summary),
    ).reset_index()

    metrics["delivery_share"] = (
        metrics["delivery_restaurant_count"] / metrics["restaurant_count"].replace({0: pd.NA})
    )
    metrics["choice_access_score"] = (
        metrics["restaurant_count"].rank(pct=True).fillna(0) * 60
        + metrics["cuisine_diversity"].rank(pct=True).fillna(0) * 40
    ).round(1)
    metrics["affordability_pressure"] = (
        metrics["median_delivery_fee"].rank(pct=True).fillna(0) * 50
        + metrics["median_minimum_order"].rank(pct=True).fillna(0) * 50
    ).round(1)
    return metrics


def available_cuisines(data: pd.DataFrame) -> list[str]:
    cuisines = sorted({cuisine for row in data["cuisine_list"] for cuisine in row})
    return ["All", *cuisines]


def restaurant_rows_for_area(data: pd.DataFrame, area_id: str | None) -> pd.DataFrame:
    if not area_id:
        return data.head(0)
    cols = [
        "restaurant_name",
        "cuisine_names",
        "rating_star",
        "delivery_fee",
        "minimum_delivery_value",
        "delivery_eta_lower_minutes",
        "delivery_eta_upper_minutes",
        "drive_distance_meters",
        "is_delivery",
        "restaurant_url",
    ]
    rows = data[data["area_id"] == area_id][[col for col in cols if col in data.columns]].copy()
    return rows.sort_values(["is_delivery", "rating_star"], ascending=[False, False]).head(200)

