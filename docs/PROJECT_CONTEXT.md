# Delivery Map Dashboard Context

Last updated: 2026-06-24

## Purpose

This repository is a standalone dashboard project for DFRE delivery availability analysis. It should remain separate from the scraping and cloud pipeline repositories.

The dashboard is intended to show where restaurants can deliver, projected from representative postcode crawl results back to statistical areas:

- England/Wales: LSOA
- Scotland: Data Zone

The current MVP deliberately keeps the first page simple: an interactive delivery map with selectable metrics by area. It is map-first rather than a BigQuery/table dashboard.

## Data Scope

Current metrics:

- `deliverable_restaurant_count`
- `fast_food_restaurant_count`
- `fast_food_restaurant_share`
- `open_restaurant_count`
- `open_restaurant_share`

Current source tables:

- `delivery_availability.postcode_restaurant_delivery_map`
- `delivery_availability.restaurant_profile`

Important distinction:

- Use the static postcode-to-restaurant delivery map for the current MVP.
- Do not use temporal/open-now snapshot tables for the static coverage, total restaurant, or fast-food metrics.
- The opening-time metrics use `delivery_availability.restaurant_opening_times`, not snapshot open-now data.
- Snapshot data can be added later as a separate time interaction layer if the dashboard needs observed crawl-window availability.

The static source currently has a label value `weekday_full_20260520`. In the dashboard and derived table this is treated as `coverage_label`, not as an open-now snapshot.

## Area Projection

The source crawl is postcode-level, but the dashboard should be interpreted at the LSOA / Data Zone level.

The project uses one representative postcode per LSOA / Data Zone from:

```text
C:\Users\sipoX\Documents\DFRE\code\WebscrapingDeliveryAvailability\data\input
```

Derived BigQuery/local cache:

- `delivery_availability.area_representative_postcodes`
- `delivery_availability.area_delivery_coverage`
- `delivery_availability.area_opening_coverage`
- `data/cache/area_delivery_coverage.parquet`
- `data/cache/opening_by_hour/*.parquet`
- `data/cache/parent_opening_by_hour/*.parquet`

The coverage table joins representative postcodes to `postcode_restaurant_delivery_map` and counts full deliverable restaurants for each area.

The opening coverage table expands `restaurant_opening_times` into day/hour availability and joins it back to area-level deliverability. It currently uses delivery opening intervals. A collection/delivery selector is a future UI addition.

Fast-food metrics are rule-based. Grocery/non-restaurant categories are excluded from the denominator, and a selected set of strong fast-food cuisine tags is counted in the numerator. See `docs/FAST_FOOD_METRIC_NOTES.md`.

## Boundary Strategy

Rendering all LSOA/Data Zone polygons at first load is too slow. The current design uses a two-level parent/child strategy inspired by the colleague dashboard pattern:

- Initial view loads only Local Authority District polygons.
- Child LSOA/Data Zone polygons are split into per-LAD GeoJSON tiles.
- Selecting a LAD loads only that LAD's child tile.
- Multiple LADs can be selected for comparison.
- LAD boundaries are filtered to LADs present in the delivery coverage table. Northern Ireland is excluded because the current representative-postcode crawl coverage is GB-only.
- In child view, a LAD boundary/click choropleth is kept underneath the child LSOA/Data Zone choropleth. This preserves child hover while still allowing unselected LADs to be clicked.

Generated boundary/cache artifacts:

- `data/boundaries/uk_lad_2024_bgc_simplified.geojson`
- `data/boundaries/children_by_parent/*.geojson`
- `data/cache/area_parent_lookup.parquet`
- `data/cache/parent_delivery_coverage.parquet`

These generated files are not intended for git. Rebuild them with `scripts/download_boundaries.py` and `scripts/build_parent_tiles.py`.

Do not reintroduce all UK LAD boundaries into the visible app unless the coverage table is also expanded. Showing Northern Ireland boundaries without coverage is confusing for this dashboard.

## Current Interaction Contract

The map should behave as follows:

- Clicking an unselected LAD adds it to the selection.
- Clicking selected LAD space or hovering child areas should not deselect anything.
- Selection is add-only from the map.
- Clearing selection happens only via the `Clear selection` button.
- Map pan/zoom should be preserved when LADs are selected.
- LAD outlines should always remain visible.
- When child areas are visible, hover should show LSOA/Data Zone information.
- The colour scale should recalculate for the currently visible selected child areas.

Current implementation approach:

- Child LSOA/DZ choropleth is the main visible data layer after selection.
- A coverage-only LAD choropleth remains underneath the child layer as the boundary/click target.
- The child layer is above the LAD layer, so selected-area hover returns LSOA/Data Zone information rather than toggling selection.
- Selected LAD outlines are reinforced with a lightweight line layer.
- Static metrics update via Plotly `Patch`; in child view the metric trace is index 1 because index 0 is the LAD boundary/click trace.
- Time controls are visible only when the selected metric starts with `open_`.

## Near-Term Next Steps

Likely next dashboard additions:

- Details panel after selecting/hovering an LSOA/Data Zone.
- Restaurant list for selected child area.
- Delivery/collection selector for opening-time metrics.
- Time-window interaction using snapshot tables, if observed crawl-window availability is needed.
- Restaurant category filters after classification is available.
- Menu analysis layers by postcode/area.

Before adding these, keep the default first view minimal and map-first.

## GitHub Preparation

Recommended files to commit:

- Application code under `delivery_dashboard/`
- `app.py`
- scripts under `scripts/`
- `README.md`
- `.env.example`
- `.gitignore`
- `requirements.txt`
- docs under `docs/`

Recommended files to leave out:

- `.venv/`
- `.env`
- `__pycache__/`
- raw downloaded boundary files
- simplified/generated GeoJSON outputs
- child tile outputs
- parquet cache files

The repository should be reproducible from scripts and environment config rather than storing heavy generated data.
