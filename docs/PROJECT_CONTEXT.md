# Delivery Map Dashboard Context

Last updated: 2026-06-22

## Purpose

This repository is a standalone dashboard project for DFRE delivery availability analysis. It should remain separate from the scraping and cloud pipeline repositories.

The dashboard is intended to show where restaurants can deliver, projected from representative postcode crawl results back to statistical areas:

- England/Wales: LSOA
- Scotland: Data Zone

The current MVP deliberately keeps the first page simple: an interactive delivery map with deliverable restaurant counts by area.

## Data Scope

Current metric:

- `deliverable_restaurant_count`

Current source tables:

- `delivery_availability.postcode_restaurant_delivery_map`
- `delivery_availability.restaurant_profile`

Important distinction:

- Use the static postcode-to-restaurant delivery map for the current MVP.
- Do not use temporal/open-now snapshot tables for the static coverage metric.
- Snapshot data can be added later as a separate time interaction layer.

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
- `data/cache/area_delivery_coverage.parquet`

The coverage table joins representative postcodes to `postcode_restaurant_delivery_map` and counts full deliverable restaurants for each area.

## Boundary Strategy

Rendering all LSOA/Data Zone polygons at first load is too slow. The current design uses a two-level parent/child strategy inspired by the colleague dashboard pattern:

- Initial view loads only Local Authority District polygons.
- Child LSOA/Data Zone polygons are split into per-LAD GeoJSON tiles.
- Selecting a LAD loads only that LAD's child tile.
- Multiple LADs can be selected for comparison.

Generated boundary/cache artifacts:

- `data/boundaries/uk_lad_2024_bgc_simplified.geojson`
- `data/boundaries/children_by_parent/*.geojson`
- `data/cache/area_parent_lookup.parquet`
- `data/cache/parent_delivery_coverage.parquet`

These generated files are not intended for git. Rebuild them with `scripts/download_boundaries.py` and `scripts/build_parent_tiles.py`.

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
- Unselected LADs remain as transparent click targets for adding more LADs.
- LAD outlines are drawn as non-interactive Mapbox line layers.

## Near-Term Next Steps

Likely next dashboard additions:

- Details panel after selecting/hovering an LSOA/Data Zone.
- Restaurant list for selected child area.
- Time-window interaction using snapshot tables.
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
