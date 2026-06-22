# Fast Food Metric Notes

Last updated: 2026-06-22

## Purpose

This note documents the current fast-food metric used in the DFRE delivery map dashboard. It is intended as a short reporting reference for how cuisine/category labels were cleaned, which labels were treated as strong fast food, and how the dashboard calculates the fast-food share.

## Source Data

The metric uses the static full-coverage delivery tables:

- `delivery_availability.postcode_restaurant_delivery_map`
- `delivery_availability.restaurant_profile`

It does not use temporal/open-now snapshot tables.

The dashboard analysis table is:

- `delivery_availability.area_delivery_coverage`

The local dashboard cache is:

- `data/cache/area_delivery_coverage.parquet`

Current area coverage:

| Metric | Value |
|---|---:|
| LSOA / Data Zone rows | 43,064 |
| LAD parent rows | 350 |
| Areas with at least one food restaurant | 41,927 |

## Cuisine Label Cleaning

`restaurant_profile.cuisine_names` contains comma-separated labels. These labels include a mixture of cuisine types, product categories, dietary attributes, platform marketing tags, and retail/non-restaurant categories.

The current cleaning rule works at the label level, not at the restaurant-row level. For example, if a restaurant has:

```text
Deals, Burgers
```

then `Deals` is removed, but the restaurant is still counted under `Burgers`.

After removing platform marketing and retail/non-restaurant labels, the current food/cuisine tag list contains:

| Metric | Value |
|---|---:|
| Food/cuisine labels retained | 173 |

## Removed Labels

The current dashboard excludes the following labels from the food denominator and cuisine/category distribution.

### Platform / Editorial Labels

| Removed label | Restaurant count |
|---|---:|
| Deals | 53,135 |
| Collect stamps | 28,709 |
| Freebies | 10,842 |
| Cheeky Tuesday | 8,695 |
| Local Legends | 735 |

### Retail / Non-Restaurant Labels

| Removed label | Restaurant count |
|---|---:|
| Groceries | 15,950 |
| Alcohol | 11,300 |
| Convenience | 3,190 |
| Shops | 1,179 |
| Pharmacy | 715 |
| Health and Beauty | 470 |
| Electronics | 420 |
| Beauty | 107 |
| Flowers | 4 |

The code also excludes a few low-frequency retail variants if they appear later, including `Supermarket`, `Supermarkets`, `Off Licence`, `Pet Shop`, `Pet-Supplies`, `Household`, `Gifts`, and `All Night Alcohol`.

## Retained Non-Cuisine Food Labels

Some labels are not classical cuisine names, but are retained because they represent food supply or meaningful delivery categories:

- Product/category labels: `Coffee`, `Desserts`, `Cakes`, `Milkshakes`, `Bubble Tea`, `Bakery`, `Sweets`, `Ice Cream`, `Drinks`, `Smoothies`
- Dietary/attribute labels: `Halal`, `Vegetarian`, `Vegan`, `Healthy`, `Gluten Free`, `Organic`
- Meal occasion labels: `Breakfast`, `Lunch`, `Brunch`, `Dinner`

These are retained for now because they are useful for food environment analysis and dashboard filtering.

## Strong Fast Food Labels

The current fast-food classification is conservative. It marks only labels that are clearly fast-food-like or takeaway-fast-food categories.

| Fast food label | Restaurant count |
|---|---:|
| Burgers | 17,398 |
| Pizza | 15,628 |
| Chicken | 14,587 |
| Kebab | 8,730 |
| Fish & Chips | 4,838 |
| Peri Peri | 1,154 |
| Fast Food | 323 |
| Italian Pizza | 297 |
| Gourmet Burgers | 119 |
| Hot Dogs | 96 |
| Authentic Pizza | 69 |
| Parmesans | 20 |
| Subways | 9 |

These labels are stored in the code as `FAST_FOOD_TAGS`.

Important caveat: a restaurant can have multiple cuisine labels. The dashboard therefore counts fast-food restaurants by distinct `restaurant_id`, not by number of matched labels. A restaurant tagged as both `Burgers` and `Pizza` is counted once in `fast_food_restaurant_count`.

## Dashboard Metrics

The current dashboard analysis table adds:

| Column | Definition |
|---|---|
| `deliverable_restaurant_count` | Distinct deliverable `restaurant_id` count, before removing retail/non-restaurant labels |
| `food_restaurant_count` | Distinct deliverable `restaurant_id` count after removing retail/non-restaurant labels from the denominator |
| `fast_food_restaurant_count` | Distinct deliverable food restaurants with at least one strong fast-food label |
| `fast_food_restaurant_share` | `fast_food_restaurant_count / food_restaurant_count` |

Current dashboard-level summary:

| Metric | Value |
|---|---:|
| Sum of deliverable area-restaurant links | 13,145,187 |
| Sum of food area-restaurant links | 10,340,609 |
| Sum of fast-food area-restaurant links | 5,080,474 |
| Overall fast-food share | 49.1% |
| Median LSOA/Data Zone fast-food share | 50.4% |
| Median LAD fast-food share | 50.4% |

The summed counts above are area-restaurant delivery opportunities. The same restaurant can appear in multiple areas if it delivers to multiple representative postcodes.

## Current Dashboard Implementation

The dashboard currently supports three map metrics:

- Total restaurants
- Fast food restaurants
- Fast food share

The metric selector changes:

- LAD overview choropleth colouring
- selected LAD child LSOA/Data Zone choropleth colouring
- map title
- colour bar title

Hover information includes:

- total deliverable restaurants
- food restaurant count
- fast food restaurant count
- fast food share

## Planned Dashboard Extensions

Likely next additions:

- Add an LSOA/Data Zone click panel with detailed area information.
- Add a restaurant list for the selected area.
- Add category filters using the cleaned cuisine/category label table.
- Add time interaction using temporal snapshot tables, clearly separated from the static full-coverage metric.
- Add restaurant opening-time or open-now layers.
- Add menu-derived indicators by postcode/area.
- Add a configurable taxonomy file for cuisine grouping, fast-food tagging, product categories, dietary attributes, and retail exclusions.

## Methodological Caveats

There is no official UK cuisine-label standard that maps Just Eat cuisine tags directly to fast food. Official UK classifications such as SIC or food hygiene business types classify business activity or establishment type, not platform cuisine labels.

The current `strong_fast_food` flag is therefore a transparent, reproducible research taxonomy. It should be reported as a rule-based classification rather than an official fast-food definition.
