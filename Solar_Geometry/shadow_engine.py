"""
Shadow Casting Engine  (Task 2)
================================
依建物高度與太陽位置，計算每棟建物在地面投射的陰影多邊形，
並對全區域進行 Unary Union 產出「總陰影遮罩多邊形」。

座標系處理：
  - 輸入 Shapefile：EPSG:3826（TWD97 / TM2 zone 121，單位：公尺）
  - 幾何計算全程在 EPSG:3826 下進行（確保距離單位正確）
  - 最終輸出轉換至 EPSG:4326（WGS84 經緯度）供地圖渲染

陰影公式：
  L = H / tan(θ)
  L：陰影長度（公尺）
  H：建物高度（公尺，來自 BUILD_H 欄位）
  θ：太陽高度角（弧度，須 > 0）

陰影方向：太陽方位角 + 180°（陰影落在太陽的對側）
  dx = L × sin(shadow_azimuth_rad)
  dy = L × cos(shadow_azimuth_rad)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon, MultiPolygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.affinity import translate

from solar_engine import SolarPosition


# ── 常數 ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SHP_PATH = PROJECT_ROOT / "Daan_Buildings" / "Buildings_Daan.shp"

SRC_CRS  = "EPSG:3826"   # 輸入投影座標
OUT_CRS  = "EPSG:4326"   # 輸出地理座標（WGS84）
MIN_ELEV = 2.0           # 高度角門檻（°）：低於此值陰影過長，略過

# 最長陰影上限（公尺）：避免低仰角時陰影長度爆炸
MAX_SHADOW_LEN = 500.0


# ── 資料模型 ──────────────────────────────────────────────────────────────────
@dataclass
class ShadowResult:
    """單次計算的陰影結果快照"""
    solar_position: SolarPosition
    shadow_gdf: gpd.GeoDataFrame      # 各建物陰影多邊形（WGS84）
    union_polygon: gpd.GeoDataFrame   # Unary Union 總遮罩（WGS84）
    n_buildings_total: int
    n_buildings_shadow: int           # 實際產生陰影的建物數
    mean_shadow_length_m: float


# ── 建物資料載入（帶快取）────────────────────────────────────────────────────
_buildings_cache: gpd.GeoDataFrame | None = None


def load_buildings(shp_path: str | Path = SHP_PATH) -> gpd.GeoDataFrame:
    """
    載入大安區建物 Shapefile，過濾無效高度，保留 EPSG:3826 座標。
    結果會快取，避免重複 I/O。
    """
    global _buildings_cache
    if _buildings_cache is not None:
        return _buildings_cache

    gdf = gpd.read_file(shp_path)
    # 確認 / 強制設定來源 CRS
    if gdf.crs is None:
        gdf = gdf.set_crs(SRC_CRS)

    # 過濾高度 <= 0（無效建物）
    gdf = gdf[gdf["BUILD_H"] > 0].copy()
    gdf = gdf.reset_index(drop=True)

    _buildings_cache = gdf
    return gdf


# ── 核心陰影計算 ──────────────────────────────────────────────────────────────
def _shadow_offset(
    height_m: float, elevation_deg: float, azimuth_deg: float
) -> tuple[float, float]:
    """
    計算單一建物的陰影偏移向量 (dx, dy)，單位：公尺（EPSG:3826）。

    Returns (0, 0) 若高度角過低（陰影超出上限）。
    """
    elev_rad = math.radians(elevation_deg)
    shadow_len = height_m / math.tan(elev_rad)

    if shadow_len > MAX_SHADOW_LEN:
        shadow_len = MAX_SHADOW_LEN

    # 陰影方向 = 太陽方位角 + 180°
    shadow_dir_rad = math.radians((azimuth_deg + 180.0) % 360.0)
    dx = shadow_len * math.sin(shadow_dir_rad)
    dy = shadow_len * math.cos(shadow_dir_rad)
    return dx, dy


def _ring_shadow_quads(coords, dx: float, dy: float) -> list[Polygon]:
    """Create side-wall quads between a ring and its translated copy."""
    quads: list[Polygon] = []
    for i in range(len(coords) - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        quad = Polygon([
            (x1, y1),
            (x2, y2),
            (x2 + dx, y2 + dy),
            (x1 + dx, y1 + dy),
        ])
        if not quad.is_empty and quad.is_valid and quad.area > 0:
            quads.append(quad)
    return quads


def _extrude_polygon_shadow(geom: Polygon, dx: float, dy: float) -> BaseGeometry:
    """Project a polygon footprint into a filled 2D shadow polygon."""
    shifted = translate(geom, xoff=dx, yoff=dy)
    pieces: list[BaseGeometry] = [geom, shifted]

    pieces.extend(_ring_shadow_quads(list(geom.exterior.coords), dx, dy))
    for interior in geom.interiors:
        pieces.extend(_ring_shadow_quads(list(interior.coords), dx, dy))

    return unary_union(pieces)


def _build_shadow_geometry(geom: BaseGeometry, dx: float, dy: float) -> BaseGeometry:
    """Handle Polygon and MultiPolygon building footprints."""
    if isinstance(geom, Polygon):
        return _extrude_polygon_shadow(geom, dx, dy)
    if isinstance(geom, MultiPolygon):
        return unary_union([
            _extrude_polygon_shadow(part, dx, dy)
            for part in geom.geoms
            if not part.is_empty
        ])
    shifted = translate(geom, xoff=dx, yoff=dy)
    return unary_union([geom, shifted]).convex_hull


def compute_shadow_polygons(
    solar_pos: SolarPosition,
    buildings: gpd.GeoDataFrame | None = None,
    build_union: bool = True,
) -> ShadowResult:
    """
    計算指定太陽位置下，所有建物的陰影多邊形並可選擇是否執行 Unary Union。

    Parameters
    ----------
    solar_pos : SolarPosition
        來自 solar_engine 的太陽位置快照（包含高度角與方位角）。
    buildings : GeoDataFrame, optional
        已載入的建物資料（EPSG:3826）。若為 None 則自動從磁碟載入。
    build_union : bool, optional
        是否建立 Unary Union 總遮罩（預設 True）。
    """
    if buildings is None:
        buildings = load_buildings()

    n_total = len(buildings)

    # 高度角不足 → 無日照陰影
    if solar_pos.elevation < MIN_ELEV:
        empty_gdf = gpd.GeoDataFrame(geometry=[], crs=OUT_CRS)
        return ShadowResult(
            solar_position=solar_pos,
            shadow_gdf=empty_gdf,
            union_polygon=empty_gdf,
            n_buildings_total=n_total,
            n_buildings_shadow=0,
            mean_shadow_length_m=0.0,
        )

    elev_deg = solar_pos.elevation
    az_deg   = solar_pos.azimuth

    shadow_polys = []
    shadow_lengths = []

    for _, row in buildings.iterrows():
        geom: BaseGeometry = row.geometry
        h: float = float(row["BUILD_H"])
        if h <= 0 or geom is None or geom.is_empty:
            continue

        dx, dy = _shadow_offset(h, elev_deg, az_deg)
        shadow_len = math.hypot(dx, dy)

        # 將 footprint 沿陰影向量外擴，補齊中間掃掠區域。
        shadow_poly = _build_shadow_geometry(geom, dx, dy)

        shadow_polys.append({
            "BUILD_ID":    row.get("BUILD_ID", ""),
            "BUILD_H":     h,
            "shadow_len":  round(shadow_len, 2),
            "geometry":    shadow_poly,
        })
        shadow_lengths.append(shadow_len)

    if not shadow_polys:
        empty_gdf = gpd.GeoDataFrame(geometry=[], crs=OUT_CRS)
        return ShadowResult(
            solar_position=solar_pos,
            shadow_gdf=empty_gdf,
            union_polygon=empty_gdf,
            n_buildings_total=n_total,
            n_buildings_shadow=0,
            mean_shadow_length_m=0.0,
        )

    # 建立 GeoDataFrame（EPSG:3826）→ 轉 WGS84
    shadow_gdf = gpd.GeoDataFrame(shadow_polys, crs=SRC_CRS).to_crs(OUT_CRS)

    if build_union:
        # Unary Union：合併重疊陰影為總遮罩
        union_geom = unary_union(shadow_gdf.geometry)
        union_gdf = gpd.GeoDataFrame(
            [{"geometry": union_geom, "offset_minutes": solar_pos.offset_minutes}],
            crs=OUT_CRS,
        )
    else:
        union_gdf = gpd.GeoDataFrame(geometry=[], crs=OUT_CRS)

    return ShadowResult(
        solar_position=solar_pos,
        shadow_gdf=shadow_gdf,
        union_polygon=union_gdf,
        n_buildings_total=n_total,
        n_buildings_shadow=len(shadow_polys),
        mean_shadow_length_m=float(pd.Series(shadow_lengths).mean()),
    )


def compute_shadow_timeslices(
    solar_positions: list[SolarPosition],
    buildings: gpd.GeoDataFrame | None = None,
) -> list[ShadowResult]:
    """
    對一組時間分片的太陽位置批次計算陰影。

    Parameters
    ----------
    solar_positions : list[SolarPosition]
        來自 get_solar_positions_over_walk() 的時間分片列表。
    buildings : GeoDataFrame, optional
        預先載入的建物資料，避免重複 I/O。

    Returns
    -------
    list[ShadowResult]
        按時間順序排列的陰影計算結果列表。
    """
    if buildings is None:
        buildings = load_buildings()

    return [
        compute_shadow_polygons(pos, buildings=buildings)
        for pos in solar_positions
    ]
