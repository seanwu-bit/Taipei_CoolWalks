"""
Integrate dynamic shadow and microclimate outputs into the static greenery network.

Route-level geometry is loaded only from StaticGreen_and_RoadBase/Output_Data
through Solar_Geometry.network_loader so static and dynamic analyses share
the exact same network input.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
STATIC_DIR = PROJECT_ROOT / "StaticGreen_and_RoadBase"
STATIC_SOURCE_DIR = STATIC_DIR / "Output_Data"
OUTPUT_DIR = PROJECT_ROOT / "Output_Data"
SOLAR_DIR = PROJECT_ROOT / "solar_geometry"

if str(SOLAR_DIR) not in sys.path:
    sys.path.insert(0, str(SOLAR_DIR))

try:
    from Solar_Geometry.network_loader import (
        RESTORED_NETWORK_NAME,
        SEGMENTED_NETWORK_NAME,
        load_restored_network,
        load_segmented_network,
    )
    from Solar_Geometry.shadow_engine import compute_shadow_polygons, load_buildings
    from Solar_Geometry.solar_engine import get_solar_position
    from Solar_Geometry.weather_engine import fetch_weather
except ModuleNotFoundError:
    from network_loader import (
        RESTORED_NETWORK_NAME,
        SEGMENTED_NETWORK_NAME,
        load_restored_network,
        load_segmented_network,
    )
    from shadow_engine import compute_shadow_polygons, load_buildings
    from solar_engine import get_solar_position
    from weather_engine import fetch_weather


TAIPEI_TZ = timezone(timedelta(hours=8))
DAAN_CENTER_LAT = 25.0264
DAAN_CENTER_LON = 121.5435

TOPOLOGY_COLS = ["u", "v", "key", "osmid"]
STATIC_KEEP_COLS = ["name", "length", "shading_index", "safety_score"]
DYNAMIC_KEEP_COLS = [
    "dynamic_shadow_ratio",
    "dynamic_wbgt_c",
    "dynamic_temperature_c",
    "dynamic_uv_index",
    "dynamic_pm25_kriging",
]


@dataclass
class IntegrationPaths:
    segmented_csv: Path
    restored_csv: Path
    restored_geojson: Path
    output_segmented_csv: Path
    output_segmented_geojson: Path
    output_segmented_gpkg: Path
    output_restored_csv: Path
    output_restored_geojson: Path
    output_restored_gpkg: Path
    output_restored_graphml: Path


def build_paths(output_suffix: str) -> IntegrationPaths:
    return IntegrationPaths(
        segmented_csv=STATIC_SOURCE_DIR / f"{SEGMENTED_NETWORK_NAME}.csv",
        restored_csv=STATIC_SOURCE_DIR / f"{RESTORED_NETWORK_NAME}.csv",
        restored_geojson=STATIC_SOURCE_DIR / f"{RESTORED_NETWORK_NAME}.geojson",
        output_segmented_csv=OUTPUT_DIR / f"Daan_Shaded_Network(分段)_{output_suffix}.csv",
        output_segmented_geojson=OUTPUT_DIR / f"Daan_Shaded_Network(分段)_{output_suffix}.geojson",
        output_segmented_gpkg=OUTPUT_DIR / f"Daan_Shaded_Network(分段)_{output_suffix}.gpkg",
        output_restored_csv=OUTPUT_DIR / f"Daan_Shaded_Network(還原)_{output_suffix}.csv",
        output_restored_geojson=OUTPUT_DIR / f"Daan_Shaded_Network(還原)_{output_suffix}.geojson",
        output_restored_gpkg=OUTPUT_DIR / f"Daan_Shaded_Network(還原)_{output_suffix}.gpkg",
        output_restored_graphml=OUTPUT_DIR / f"Daan_Shaded_Network(還原)_{output_suffix}.graphml",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Integrate dynamic shadow into the static greenery network.")
    parser.add_argument("--date", help="Local date in YYYY-MM-DD. Default: today in UTC+8.")
    parser.add_argument("--time", help="Local time in HH:MM. Default: current time in UTC+8 rounded to minute.")
    parser.add_argument("--lat", type=float, default=DAAN_CENTER_LAT, help="Solar calculation latitude.")
    parser.add_argument("--lon", type=float, default=DAAN_CENTER_LON, help="Solar calculation longitude.")
    parser.add_argument(
        "--output-suffix",
        default="dynamic_v1",
        help="Suffix used in output filenames, e.g. dynamic_v1.",
    )
    parser.add_argument(
        "--max-climate-gap-minutes",
        type=int,
        default=90,
        help="Maximum allowed gap between simulation time and weather/AQI timestamps.",
    )
    return parser.parse_args()


def resolve_departure_local(args: argparse.Namespace) -> datetime:
    now_local = datetime.now(TAIPEI_TZ).replace(second=0, microsecond=0)
    if not args.date and not args.time:
        return now_local

    local_date = now_local.date() if not args.date else datetime.strptime(args.date, "%Y-%m-%d").date()
    local_time = now_local.time().replace(second=0, microsecond=0)
    if args.time:
        parsed_time = datetime.strptime(args.time, "%H:%M").time()
        local_time = parsed_time.replace(second=0, microsecond=0)
    return datetime(
        local_date.year,
        local_date.month,
        local_date.day,
        local_time.hour,
        local_time.minute,
        tzinfo=TAIPEI_TZ,
    )


def clean_attributes(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    for col in gdf.columns:
        if col == "geometry":
            continue
        series = gdf[col]
        if series.dtype == "object" or series.apply(lambda x: isinstance(x, (list, dict))).any():
            gdf[col] = series.astype(str)
    return gdf


def normalize_graph_id_series(series: pd.Series) -> pd.Series:
    def normalize_value(value: object) -> str:
        if pd.isna(value):
            return ""
        text = str(value).strip()
        try:
            numeric = float(text)
        except ValueError:
            return text
        if numeric.is_integer():
            return str(int(numeric))
        return text

    return series.map(normalize_value)


def load_static_layers() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    segmented_edges, nodes = load_segmented_network()
    restored_edges, _ = load_restored_network()
    return segmented_edges, restored_edges, nodes


def compute_shadow_ratio(
    edges: gpd.GeoDataFrame,
    departure_local: datetime,
    lat: float,
    lon: float,
    ratio_mode: str = "area",
) -> gpd.GeoDataFrame:
    solar_pos = get_solar_position(departure_local, lat, lon)
    buildings = load_buildings()
    shadow_result = compute_shadow_polygons(solar_pos, buildings=buildings, build_union=True)

    enriched = edges.copy()
    enriched["dynamic_shadow_ratio"] = 0.0

    if shadow_result.union_polygon.empty:
        return enriched

    edge_proj = enriched.to_crs(epsg=3826)
    shadow_union_proj = shadow_result.union_polygon.to_crs(epsg=3826)
    union_geom = shadow_union_proj.geometry.iloc[0]

    if ratio_mode == "length":
        base_len = edge_proj.geometry.length
        hit_len = edge_proj.geometry.intersection(union_geom).length
        enriched["dynamic_shadow_ratio"] = (
            hit_len / base_len.replace(0, pd.NA)
        ).fillna(0.0).clip(lower=0.0, upper=1.0).round(6)
        return enriched

    edge_area = edge_proj.geometry.area
    shadow_area = edge_proj.geometry.intersection(union_geom).area
    enriched["dynamic_shadow_ratio"] = (
        shadow_area / edge_area.replace(0, pd.NA)
    ).fillna(0.0).clip(lower=0.0, upper=1.0).round(6)
    return enriched


def attach_dynamic_climate(
    segmented_edges: gpd.GeoDataFrame,
    departure_local: datetime,
    max_climate_gap_minutes: int,
) -> gpd.GeoDataFrame:
    enriched = segmented_edges.copy()
    climate_cols = [
        "dynamic_wbgt_c",
        "dynamic_temperature_c",
        "dynamic_uv_index",
        "dynamic_pm25_kriging",
    ]
    for col in climate_cols:
        enriched[col] = pd.NA

    weather = fetch_weather(
        target_time=departure_local,
        max_time_gap_minutes=max_climate_gap_minutes,
        strict_time_sync=False,
    )
    enriched["dynamic_wbgt_c"] = weather.wbgt
    enriched["dynamic_temperature_c"] = weather.temperature
    enriched["dynamic_uv_index"] = weather.uv_index
    enriched["dynamic_pm25_kriging"] = weather.pm25_kriging
    return enriched


def aggregate_segments_to_restored(segmented_edges: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    raise NotImplementedError("Use restored network direct dynamic computation instead of osmid/key aggregation.")


def select_output_columns(edges: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    keep_cols = TOPOLOGY_COLS + STATIC_KEEP_COLS + DYNAMIC_KEEP_COLS
    available = [col for col in keep_cols if col in edges.columns]
    return edges[available + ["geometry"]].copy()


def export_outputs(
    segmented_edges: gpd.GeoDataFrame,
    restored_edges: gpd.GeoDataFrame,
    nodes: gpd.GeoDataFrame,
    paths: IntegrationPaths,
) -> None:
    segmented_edges = select_output_columns(segmented_edges)
    restored_edges = select_output_columns(restored_edges)

    pd.DataFrame(segmented_edges.drop(columns="geometry")).to_csv(paths.output_segmented_csv, index=False)
    segmented_out = clean_attributes(segmented_edges.copy())
    segmented_out.to_file(paths.output_segmented_geojson, driver="GeoJSON")
    segmented_out.to_file(paths.output_segmented_gpkg, layer="edges", driver="GPKG")
    clean_attributes(nodes.copy()).to_file(paths.output_segmented_gpkg, layer="nodes", driver="GPKG")

    pd.DataFrame(restored_edges.drop(columns="geometry")).to_csv(paths.output_restored_csv, index=False)
    restored_out = clean_attributes(restored_edges.copy())
    restored_out.to_file(paths.output_restored_geojson, driver="GeoJSON")
    restored_out.to_file(paths.output_restored_gpkg, layer="edges", driver="GPKG")
    clean_attributes(nodes.copy()).to_file(paths.output_restored_gpkg, layer="nodes", driver="GPKG")

    export_graphml(nodes=nodes, restored_edges=restored_edges, graphml_path=paths.output_restored_graphml)


def export_graphml(
    nodes: gpd.GeoDataFrame,
    restored_edges: gpd.GeoDataFrame,
    graphml_path: Path,
) -> None:
    graphml_path.parent.mkdir(parents=True, exist_ok=True)

    gdf_nodes = nodes.copy()
    if gdf_nodes.crs is not None and gdf_nodes.crs.to_epsg() != 4326:
        gdf_nodes = gdf_nodes.to_crs(epsg=4326)
    if "osmid" in gdf_nodes.columns:
        gdf_nodes["osmid"] = normalize_graph_id_series(gdf_nodes["osmid"])
        gdf_nodes = gdf_nodes.drop_duplicates(subset=["osmid"]).copy()
    if "x" not in gdf_nodes.columns:
        gdf_nodes["x"] = gdf_nodes.geometry.x
    if "y" not in gdf_nodes.columns:
        gdf_nodes["y"] = gdf_nodes.geometry.y
    if "osmid" in gdf_nodes.columns:
        gdf_nodes = gdf_nodes.set_index("osmid")
    else:
        gdf_nodes = gdf_nodes[~gdf_nodes.index.duplicated(keep="first")].copy()

    gdf_edges = restored_edges.copy()
    if gdf_edges.crs is not None and gdf_edges.crs.to_epsg() != 4326:
        gdf_edges = gdf_edges.to_crs(epsg=4326)
    if "u" not in gdf_edges.columns or "v" not in gdf_edges.columns:
        raise ValueError("Missing `u` or `v` columns in restored edge layer.")
    if "key" not in gdf_edges.columns:
        gdf_edges["key"] = 0
    gdf_edges["u"] = normalize_graph_id_series(gdf_edges["u"])
    gdf_edges["v"] = normalize_graph_id_series(gdf_edges["v"])
    gdf_edges["key"] = normalize_graph_id_series(gdf_edges["key"].fillna(0))
    gdf_edges = gdf_edges[(gdf_edges["u"] != "") & (gdf_edges["v"] != "")].copy()
    gdf_edges = gdf_edges.drop_duplicates(subset=["u", "v", "key"]).copy()
    edge_index = pd.MultiIndex.from_frame(
        gdf_edges[["u", "v", "key"]].copy(),
        names=["u", "v", "key"],
    )
    gdf_edges.index = edge_index
    gdf_edges = gdf_edges.drop(columns=["u", "v", "key"])

    gdf_nodes = clean_attributes(gdf_nodes)
    gdf_edges = clean_attributes(gdf_edges)
    graph = ox.graph_from_gdfs(gdf_nodes, gdf_edges)
    ox.save_graphml(graph, graphml_path)
    if not graphml_path.exists():
        raise FileNotFoundError(f"GraphML export failed: {graphml_path}")


def main() -> None:
    args = parse_args()
    departure_local = resolve_departure_local(args)
    paths = build_paths(args.output_suffix)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading static layers from {STATIC_SOURCE_DIR}")
    print(f"Writing integrated outputs to {OUTPUT_DIR}")
    segmented_edges, restored_edges, nodes = load_static_layers()

    segmented_edges = compute_shadow_ratio(
        segmented_edges,
        departure_local,
        args.lat,
        args.lon,
        ratio_mode="area",
    )
    segmented_edges = attach_dynamic_climate(
        segmented_edges=segmented_edges,
        departure_local=departure_local,
        max_climate_gap_minutes=args.max_climate_gap_minutes,
    )

    restored_edges = compute_shadow_ratio(
        restored_edges,
        departure_local,
        args.lat,
        args.lon,
        ratio_mode="length",
    )
    restored_edges = attach_dynamic_climate(
        segmented_edges=restored_edges,
        departure_local=departure_local,
        max_climate_gap_minutes=args.max_climate_gap_minutes,
    )

    export_outputs(segmented_edges, restored_edges, nodes, paths)

    print("Dynamic integration complete.")
    print(f"Segmented CSV:  {paths.output_segmented_csv}")
    print(f"Segmented GPKG: {paths.output_segmented_gpkg}")
    print(f"Restored CSV:   {paths.output_restored_csv}")
    print(f"Restored GPKG:  {paths.output_restored_gpkg}")
    print(f"Restored GraphML: {paths.output_restored_graphml}")


if __name__ == "__main__":
    main()
