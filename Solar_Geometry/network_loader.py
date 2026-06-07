"""
Shared static network loader for route-level dynamic analysis.

All road-segment geometry used by Solar_Geometry must come from
StaticGreen_and_RoadBase/Output_Data so every downstream analysis
uses the same segmented/restored network input.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_NETWORK_DIR = PROJECT_ROOT / "StaticGreen_and_RoadBase" / "Output_Data"

SEGMENTED_NETWORK_NAME = "Daan_Shaded_Network(分段)_v1"
RESTORED_NETWORK_NAME = "Daan_Shaded_Network(還原)_v1"


@dataclass(frozen=True)
class StaticNetworkPaths:
    segmented_gpkg: Path
    restored_gpkg: Path


def get_static_network_paths() -> StaticNetworkPaths:
    return StaticNetworkPaths(
        segmented_gpkg=STATIC_NETWORK_DIR / f"{SEGMENTED_NETWORK_NAME}.gpkg",
        restored_gpkg=STATIC_NETWORK_DIR / f"{RESTORED_NETWORK_NAME}.gpkg",
    )


def _read_gpkg_layer(gpkg_path: Path, layer: str) -> gpd.GeoDataFrame:
    if not gpkg_path.exists():
        raise FileNotFoundError(f"Static network GPKG not found: {gpkg_path}")
    return gpd.read_file(gpkg_path, layer=layer)


def load_segmented_network() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    paths = get_static_network_paths()
    edges = _read_gpkg_layer(paths.segmented_gpkg, layer="edges")
    nodes = _read_gpkg_layer(paths.segmented_gpkg, layer="nodes")
    return edges, nodes


def load_restored_network() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    paths = get_static_network_paths()
    edges = _read_gpkg_layer(paths.restored_gpkg, layer="edges")
    nodes = _read_gpkg_layer(paths.restored_gpkg, layer="nodes")
    return edges, nodes
