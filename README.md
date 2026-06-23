# Delivery Map Dashboard

Plotly Dash app for exploring DFRE delivery availability as an interactive map.

This project is intentionally separate from the delivery scraping and cloud pipeline repos. The pipeline produces postcode-level Just Eat delivery coverage; this dashboard projects the representative-postcode result back to LSOA / Scottish Data Zone areas and renders the result as a fast two-level map.

## Current MVP

The current app focuses on one static metric:

- `deliverable_restaurant_count`: full number of restaurants that can deliver to each representative postcode / LSOA / Data Zone.

The metric is built from the static tables:

- `delivery_availability.postcode_restaurant_delivery_map`
- `delivery_availability.restaurant_profile`

It does not use temporal/open-now snapshot tables. Snapshot tables represent time-window availability and should be added later as a separate temporal layer, not mixed into this full-coverage MVP metric.

## Map Behaviour

The first screen is a lightweight Local Authority District overview. It avoids loading all 43,064 child polygons on initial page load.

- Overview layer: UK LAD polygons.
- Click an unselected LAD to add it to the comparison set.
- Selecting a LAD preserves the current map view; it does not auto-zoom.
- Multiple LADs can be selected together.
- LAD outlines remain visible while child areas are shown.
- When LADs are selected, only their LSOA / Data Zone child polygons are loaded.
- Hovering child polygons shows child area information and the delivery count.
- Use `Clear selection` to reset the selected LADs.

The colour scale is recalculated from the currently visible child areas, so selected LADs can be compared against each other with a local distribution.

## Project Layout

```text
app.py                                  Dash app entrypoint
delivery_dashboard/config.py            Environment/config helpers
delivery_dashboard/data.py              BigQuery and local cache loading
delivery_dashboard/geo.py               GeoJSON and area helpers
delivery_dashboard/tiles.py             Parent/child tile loading helpers
scripts/download_boundaries.py          Downloads public boundary data
scripts/build_area_delivery_coverage.py Builds static coverage table/cache
scripts/build_area_opening_coverage.py Builds hourly opening-time table/cache
scripts/build_parent_tiles.py           Builds LAD parent metrics and child tiles
scripts/simplify_boundaries.py          Optional boundary simplification utility
docs/PROJECT_CONTEXT.md                 Handoff context and design notes
```

Generated boundary files and local parquet caches are intentionally ignored by git. Rebuild them with the scripts below.

## Setup

```powershell
cd C:\Users\sipoX\Documents\DFRE\code\delivery-map-dashboard
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Update `.env` with the BigQuery project/dataset values and source paths for the representative postcode inputs.

## Build Data

Download boundary data:

```powershell
.\.venv\Scripts\python.exe scripts\download_boundaries.py
```

Build the static area coverage cache/table:

```powershell
.\.venv\Scripts\python.exe scripts\build_area_delivery_coverage.py --all --coverage-label weekday_full_20260520
```

Build the fast LAD overview and per-parent child polygon tiles:

```powershell
.\.venv\Scripts\python.exe scripts\build_parent_tiles.py
```

Build hourly delivery opening-time coverage:

```powershell
.\.venv\Scripts\python.exe scripts\build_area_opening_coverage.py --all --coverage-label weekday_full_20260520
```

This creates `area_opening_coverage` in BigQuery and local hourly parquet caches under `data/cache/opening_by_hour/` and `data/cache/parent_opening_by_hour/`.

## Run

```powershell
.\.venv\Scripts\python.exe app.py
```

Open <http://127.0.0.1:8050>.

## GitHub Notes

Commit the application code, scripts, README, context docs, and config examples. Do not commit:

- `.venv/`
- `.env`
- raw boundary downloads
- generated simplified GeoJSON files
- `data/boundaries/children_by_parent/`
- local parquet caches
- hourly opening-time parquet caches
- Python cache directories

Those files are reproducible local artifacts and are too large/noisy for the repository.
