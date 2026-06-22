from __future__ import annotations

from dash import Dash, Input, Output, State, callback, dcc, html, no_update
import dash
import plotly.express as px
import plotly.graph_objects as go

from delivery_dashboard.config import settings
from delivery_dashboard.tiles import (
    load_area_coverage_with_parent,
    load_child_geojson,
    load_parent_coverage,
    load_parent_geojson,
)


PARENT_COVERAGE = load_parent_coverage()
PARENT_GEOJSON = load_parent_geojson()
AREA_COVERAGE = load_area_coverage_with_parent()
DATA_MODE = "parent overview + lazy child tiles"
PARENT_NAME_BY_ID = dict(zip(PARENT_COVERAGE["parent_id"], PARENT_COVERAGE["parent_name"]))
MAP_UIREVISION = "delivery-map-preserve-view"
DEFAULT_CENTER = {"lat": 54.7, "lon": -3.2}
DEFAULT_ZOOM = 4.7


def selected_parent_ids(selected_parents: list[dict] | None) -> list[str]:
    if not selected_parents:
        return []
    return [str(item["parent_id"]) for item in selected_parents if item.get("parent_id")]


def selected_parent_label(selected_parents: list[dict] | None) -> str:
    if not selected_parents:
        return ""
    names = [item.get("parent_name") or item.get("parent_id") for item in selected_parents]
    if len(names) <= 3:
        return ", ".join(names)
    return f"{names[0]}, {names[1]}, {names[2]} + {len(names) - 3} more"


def empty_figure(title: str, message: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        title=title,
        template="plotly_white",
        xaxis={"visible": False},
        yaxis={"visible": False},
        annotations=[
            {
                "text": message,
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"size": 16},
            }
        ],
        uirevision=MAP_UIREVISION,
    )
    return fig


def parent_from_click(click_data) -> dict | None:
    if not click_data or not click_data.get("points"):
        return None
    point = click_data["points"][0]
    custom = point.get("customdata") or []
    if len(custom) >= 2 and custom[0] is not None:
        parent_id = str(custom[0])
        if parent_id in PARENT_NAME_BY_ID:
            return {"parent_id": parent_id, "parent_name": str(custom[1])}
    location = point.get("location")
    if location:
        parent_id = str(location)
        parent_name = PARENT_NAME_BY_ID.get(parent_id)
        if parent_name:
            return {"parent_id": parent_id, "parent_name": parent_name}
    return None


def add_parent_selection(selected_parents: list[dict] | None, parent: dict | None) -> list[dict]:
    selected_parents = list(selected_parents or [])
    if not parent:
        return selected_parents
    parent_id = parent["parent_id"]
    if any(item.get("parent_id") == parent_id for item in selected_parents):
        return selected_parents
    return selected_parents + [parent]


def add_parent_outline_trace(fig: go.Figure, selected_ids: list[str]) -> go.Figure:
    z_values = PARENT_COVERAGE["parent_id"].isin(selected_ids).astype(int)
    fig.add_trace(
        go.Choroplethmapbox(
            geojson=PARENT_GEOJSON,
            locations=PARENT_COVERAGE["parent_id"],
            z=z_values,
            featureidkey="properties.parent_id",
            colorscale=[
                [0, "rgba(0,0,0,0)"],
                [1, "rgba(31,41,51,0.18)"],
            ],
            showscale=False,
            marker_opacity=0.18,
            marker_line_color="#1f2933",
            marker_line_width=1.5,
            customdata=PARENT_COVERAGE[["parent_id", "parent_name"]].values,
            hovertemplate="<b>%{customdata[1]}</b><br>Click to select / deselect<extra></extra>",
            name="Local authority boundaries",
        )
    )
    return fig


def add_parent_outline_layer(fig: go.Figure) -> go.Figure:
    existing_layers = list(getattr(fig.layout.mapbox, "layers", []) or [])
    existing_layers.append(
        {
            "sourcetype": "geojson",
            "source": PARENT_GEOJSON,
            "type": "line",
            "color": "#1f2933",
            "line": {"width": 1.4},
            "opacity": 0.7,
        }
    )
    fig.update_layout(mapbox_layers=existing_layers)
    return fig


def parent_click_trace(selected_ids: list[str]) -> go.Choroplethmapbox:
    rows = PARENT_COVERAGE[~PARENT_COVERAGE["parent_id"].isin(selected_ids)].copy()
    return go.Choroplethmapbox(
        geojson=PARENT_GEOJSON,
        locations=rows["parent_id"],
        z=[1] * len(rows),
        featureidkey="properties.parent_id",
        colorscale=[
            [0, "rgba(255,255,255,0.03)"],
            [1, "rgba(255,255,255,0.03)"],
        ],
        showscale=False,
        marker_opacity=0.03,
        marker_line_width=0,
        customdata=rows[["parent_id", "parent_name"]].values,
        hovertemplate="<b>%{customdata[1]}</b><br>Click to add to selection<extra></extra>",
        name="Add local authority",
    )


def make_parent_map(selected_parents: list[dict] | None = None) -> go.Figure:
    selected_ids = selected_parent_ids(selected_parents)
    fig = px.choropleth_mapbox(
        PARENT_COVERAGE,
        geojson=PARENT_GEOJSON,
        locations="parent_id",
        featureidkey="properties.parent_id",
        color="median_deliverable_restaurant_count",
        hover_name="parent_name",
        hover_data={
            "parent_id": True,
            "child_area_count": True,
            "median_deliverable_restaurant_count": ":.0f",
            "mean_deliverable_restaurant_count": ":.0f",
            "food_restaurant_count": ":.0f",
            "fast_food_restaurant_count": ":.0f",
            "fast_food_restaurant_share": ":.1%",
            "median_food_restaurant_count": ":.0f",
            "median_fast_food_restaurant_count": ":.0f",
            "median_fast_food_restaurant_share": ":.1%",
            "min_deliverable_restaurant_count": ":.0f",
            "max_deliverable_restaurant_count": ":.0f",
        },
        custom_data=["parent_id", "parent_name"],
        color_continuous_scale="Viridis",
        mapbox_style="carto-positron",
        opacity=0.78,
        zoom=DEFAULT_ZOOM,
        center=DEFAULT_CENTER,
        height=760,
    )
    fig.update_layout(
        margin={"l": 0, "r": 0, "t": 34, "b": 0},
        title="Median deliverable restaurants by local authority",
        coloraxis_colorbar={"title": "Median restaurants"},
        uirevision=MAP_UIREVISION,
        clickmode="event",
    )
    if selected_ids:
        add_parent_outline_trace(fig, selected_ids)
    return fig


def combined_child_geojson(parent_ids: list[str]) -> dict:
    features = []
    for parent_id in parent_ids:
        features.extend(load_child_geojson(parent_id).get("features") or [])
    return {"type": "FeatureCollection", "features": features}


def make_child_map(selected_parents: list[dict]) -> go.Figure:
    parent_ids = selected_parent_ids(selected_parents)
    child_rows = AREA_COVERAGE[AREA_COVERAGE["parent_id"].isin(parent_ids)].copy()
    child_geojson = combined_child_geojson(parent_ids)
    if child_rows.empty or not child_geojson.get("features"):
        return empty_figure("Selected local authorities", "No child polygons found for the selected local authorities.")

    fig = px.choropleth_mapbox(
        child_rows,
        geojson=child_geojson,
        locations="area_id",
        featureidkey="properties.area_id",
        color="deliverable_restaurant_count",
        hover_name="area_name",
        hover_data={
            "area_id": True,
            "area_type": True,
            "parent_name": True,
            "representative_postcode": True,
            "deliverable_restaurant_count": True,
            "food_restaurant_count": True,
            "fast_food_restaurant_count": True,
            "fast_food_restaurant_share": ":.1%",
        },
        color_continuous_scale="Viridis",
        mapbox_style="carto-positron",
        opacity=0.78,
        zoom=DEFAULT_ZOOM,
        center=DEFAULT_CENTER,
        height=760,
    )
    fig.update_layout(
        margin={"l": 0, "r": 0, "t": 34, "b": 0},
        title=f"Deliverable restaurants by LSOA/Data Zone in {selected_parent_label(selected_parents)}",
        coloraxis_colorbar={"title": "Restaurants"},
        uirevision=MAP_UIREVISION,
        clickmode="event",
    )
    # Put a transparent click target above the child trace, but only for unselected
    # LADs. It does not cover selected LADs, so child-area hover remains available.
    fig.add_trace(parent_click_trace(parent_ids))
    add_parent_outline_layer(fig)
    return fig


def make_status(selected_parents: list[dict] | None) -> list[html.Div]:
    parent_ids = selected_parent_ids(selected_parents)
    if parent_ids:
        rows = AREA_COVERAGE[AREA_COVERAGE["parent_id"].isin(parent_ids)]
        values = {
            "View": "Selected local authorities",
            "Selected LADs": f"{len(parent_ids):,}",
            "Areas": f"{len(rows):,}",
            "Median restaurants": "-" if rows.empty else f"{rows['deliverable_restaurant_count'].median():.0f}",
            "Fast food share": "-"
            if rows.empty or rows["food_restaurant_count"].sum() == 0
            else f"{rows['fast_food_restaurant_count'].sum() / rows['food_restaurant_count'].sum():.1%}",
            "Coverage": "-" if rows.empty else str(rows["coverage_label"].dropna().iloc[0]),
        }
    else:
        values = {
            "View": "Local authority overview",
            "Local authorities": f"{len(PARENT_COVERAGE):,}",
            "Child areas": f"{len(AREA_COVERAGE):,}",
            "Median restaurants": f"{PARENT_COVERAGE['median_deliverable_restaurant_count'].median():.0f}",
            "Fast food share": f"{PARENT_COVERAGE['fast_food_restaurant_count'].sum() / PARENT_COVERAGE['food_restaurant_count'].sum():.1%}",
            "Data mode": DATA_MODE,
        }
    return [
        html.Div([html.Div(label, className="card-label"), html.Div(value, className="card-value")], className="metric-card")
        for label, value in values.items()
    ]


app = Dash(__name__, title="DFRE Delivery Map")
server = app.server

app.layout = html.Div(
    [
        dcc.Store(id="selected-parents", data=[]),
        html.Div(
            [
                html.Div(
                    [
                        html.H1("DFRE Delivery Map"),
                        html.Div(
                            "Click local authorities to add them to the comparison set; hover LSOA/Data Zone polygons for details.",
                            className="subtitle",
                        ),
                    ]
                ),
                html.Button("Clear selection", id="clear-button", n_clicks=0, className="back-button"),
            ],
            className="header",
        ),
        html.Div(id="metric-cards", className="metric-cards"),
        html.Div(dcc.Graph(id="map", config={"displayModeBar": True, "scrollZoom": True}), className="map-panel"),
        html.Div(
            "Static full delivery coverage. Select local authorities from the overview; hover LSOA/Data Zone polygons for details. Use Clear selection to reset.",
            className="footnote",
        ),
    ]
)


@callback(
    Output("selected-parents", "data"),
    Input("map", "clickData"),
    Input("clear-button", "n_clicks"),
    State("selected-parents", "data"),
    prevent_initial_call=True,
)
def update_selected_parents(click_data, clear_clicks, selected_parents):
    triggered = dash.callback_context.triggered[0]["prop_id"].split(".")[0]
    if triggered == "clear-button":
        return []
    return add_parent_selection(selected_parents, parent_from_click(click_data))


@callback(
    Output("map", "figure"),
    Output("metric-cards", "children"),
    Output("clear-button", "style"),
    Input("selected-parents", "data"),
)
def update_map(selected_parents):
    if selected_parent_ids(selected_parents):
        return make_child_map(selected_parents), make_status(selected_parents), {"display": "inline-flex"}
    return make_parent_map(selected_parents), make_status(selected_parents), {"display": "none"}


app.index_string = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            body { margin: 0; font-family: Arial, sans-serif; background: #f6f6f3; color: #202124; }
            .header { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 18px; align-items: end; padding: 18px 24px 14px; background: #1f2933; color: white; }
            h1 { margin: 0; font-size: 28px; letter-spacing: 0; }
            .subtitle { margin-top: 4px; color: #d5dde5; font-size: 14px; }
            .back-button { align-items: center; justify-content: center; height: 36px; padding: 0 14px; border: 1px solid #d5dde5; border-radius: 6px; color: #fff; background: transparent; cursor: pointer; }
            .metric-cards { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; padding: 14px 24px; }
            .metric-card { background: white; border: 1px solid #ddd; border-radius: 6px; padding: 12px 14px; min-height: 58px; }
            .card-label { font-size: 12px; color: #5f6368; }
            .card-value { margin-top: 4px; font-size: 22px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .map-panel { margin: 0 24px 10px; background: white; border: 1px solid #ddd; border-radius: 6px; overflow: hidden; }
            .footnote { margin: 0 24px 24px; color: #5f6368; font-size: 13px; }
            @media (max-width: 1100px) { .metric-cards { grid-template-columns: repeat(2, 1fr); } }
            @media (max-width: 900px) { .header { grid-template-columns: 1fr; } }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>{%config%}{%scripts%}{%renderer%}</footer>
    </body>
</html>
"""


if __name__ == "__main__":
    app.run_server(host=settings.dash_host, port=settings.dash_port, debug=False)

