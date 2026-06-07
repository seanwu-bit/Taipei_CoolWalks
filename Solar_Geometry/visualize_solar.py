"""
Dynamic Shadow & Microclimate — Streamlit Dashboard
=====================================================
Task 1：太陽幾何與方位演算核心 (Solar Geometry Engine)
Task 2：動態陰影投影計算 (Shadow Casting Engine)

研究範圍：台北市大安區及周邊
執行方式：streamlit run visualize_solar.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timedelta, timezone, time as dtime
import math

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import folium
from streamlit_folium import st_folium

from solar_engine import get_solar_position, get_solar_positions_over_walk, SolarPosition
from shadow_engine import (
    load_buildings, compute_shadow_polygons, ShadowResult,
)
from weather_engine import fetch_weather, WeatherData, _haversine_m

# ═══════════════════════════════════════════════════════════════════════════
# 頁面設定
# ═══════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="☀️ Dynamic Shadow & Microclimate",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main { background-color: #0f1117; }
    .metric-card {
        background: linear-gradient(135deg,#1e2130 0%,#262d40 100%);
        border:1px solid #3a4060; border-radius:12px;
        padding:18px 22px; text-align:center;
    }
    .metric-label{color:#8892b0;font-size:.78rem;letter-spacing:.08em;
        text-transform:uppercase;margin-bottom:6px}
    .metric-value{color:#e6f1ff;font-size:2rem;font-weight:700}
    .metric-unit {color:#64ffda;font-size:.85rem;margin-left:4px}
    .section-title{color:#ccd6f6;font-size:1.05rem;font-weight:600;
        border-left:3px solid #64ffda;padding-left:10px;margin:20px 0 12px 0}
    .tag-above{background:#1a4731;color:#64ffda;border-radius:6px;
        padding:2px 8px;font-size:.8rem}
    .tag-below{background:#4a1a1a;color:#ff6b6b;border-radius:6px;
        padding:2px 8px;font-size:.8rem}
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# 大安區地理常數（由 shapefile bounds 計算）
# ═══════════════════════════════════════════════════════════════════════════
DAAN_CENTER = (25.0264, 121.5435)
DAAN_BOUNDS = [[25.0077, 121.5218], [25.0452, 121.5651]]

DIRECTIONS = ["北","北北東","東北","東北東","東","東南東","東南","南南東",
              "南","南南西","西南","西南西","西","西北西","西北","北北西"]

# ═══════════════════════════════════════════════════════════════════════════
# 側邊欄：共用輸入
# ═══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## ⚙️ 參數設定")
    st.info("📍 研究範圍\n台北市大安區及周邊\n緯度 25.008°–25.045°\n經度 121.522°–121.565°")
    st.divider()
    st.markdown("### 🕐 出發時間（UTC+8）")
    use_now = st.toggle("使用目前時間", value=False)
    tz = timezone(timedelta(hours=8))

    if use_now:
        now_local   = datetime.now(tz)
        depart_date = now_local.date()
        depart_time = now_local.time().replace(second=0, microsecond=0)
    else:
        depart_date = st.date_input("出發日期", value=datetime(2025, 6, 21).date())
        depart_time = st.time_input("出發時間", value=dtime(9, 0))

    departure_local = datetime(
        depart_date.year, depart_date.month, depart_date.day,
        depart_time.hour, depart_time.minute, tzinfo=tz,
    )

    st.divider()
    st.markdown("### 🚶 步行時間分片")
    total_walk = st.slider("步行時間（分鐘）", 15, 90, 60, 15)
    interval   = st.select_slider("計算間隔（分鐘）", [5, 10, 15, 30], value=5)
    st.divider()
    show_full_day = st.toggle("顯示全日太陽軌跡", value=True)

# ═══════════════════════════════════════════════════════════════════════════
# 太陽位置計算
# ═══════════════════════════════════════════════════════════════════════════
lat, lon = DAAN_CENTER

walk_positions: list[SolarPosition] = get_solar_positions_over_walk(
    departure_local, lat, lon,
    interval_minutes=interval, total_minutes=total_walk,
)
current_pos = walk_positions[0] if walk_positions else None

# Debug: show number of positions generated
st.sidebar.write(f"生成時刻數: {len(walk_positions)}")
st.sidebar.write(f"步行時間: {total_walk} 分鐘")
st.sidebar.write(f"計算間隔: {interval} 分鐘")

if show_full_day:
    day_start = datetime(depart_date.year, depart_date.month,
                         depart_date.day, 0, 0, tzinfo=tz)
    full_day = [get_solar_position(day_start, lat, lon, m) for m in range(0, 1440, 10)]
else:
    full_day = []


def positions_to_df(positions):
    return pd.DataFrame([{
        "時間(本地)":  (p.time.astimezone(tz)).strftime("%H:%M"),
        "offset_min": p.offset_minutes + 1,
        "高度角(°)":  p.elevation,
        "方位角(°)":  p.azimuth,
        "在地平線上": p.elevation > 0,
    } for p in positions])


walk_df = positions_to_df(walk_positions)
full_df  = positions_to_df(full_day) if full_day else pd.DataFrame()

# ═══════════════════════════════════════════════════════════════════════════
# 頁籤
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("## ☀️ Dynamic Shadow & Microclimate｜台北市大安區")
tab1, tab2, tab3, tab4 = st.tabs(
    ["🌞  Task 1 — 太陽幾何演算核心",
     "🏙️  Task 2 — 動態建物陰影投影",
     "�️  Task 3 — 空氣品質空間分布",
     "�️  Task 4 — 即時氣象 & 微氣候"]
)

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  TAB 1 — Solar Geometry Engine                                           ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
with tab1:
    st.divider()
    st.markdown('<p class="section-title">📍 出發時刻太陽位置｜大安區中心</p>',
                unsafe_allow_html=True)
    kc1, kc2, kc3, kc4 = st.columns(4)
    horizon_tag = ('<span class="tag-above">地平線以上 ☀️</span>'
                   if current_pos.elevation > 0
                   else '<span class="tag-below">地平線以下 🌙</span>')
    dir_label = DIRECTIONS[round(current_pos.azimuth / 22.5) % 16]

    with kc1:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">高度角 Elevation</div>
            <div class="metric-value">{current_pos.elevation:+.2f}<span class="metric-unit">°</span></div>
            <div style="margin-top:6px">{horizon_tag}</div></div>""", unsafe_allow_html=True)
    with kc2:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">方位角 Azimuth</div>
            <div class="metric-value">{current_pos.azimuth:.2f}<span class="metric-unit">°</span></div>
            <div style="color:#8892b0;font-size:.8rem;margin-top:4px">方向：{dir_label}</div></div>""",
            unsafe_allow_html=True)
    with kc3:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">出發時間（本地 UTC+8）</div>
            <div class="metric-value" style="font-size:1.3rem">
                {departure_local.strftime("%Y/%m/%d %H:%M")}</div>
            <div style="color:#8892b0;font-size:.8rem;margin-top:4px">
                {current_pos.time.strftime("%H:%M UTC")}</div></div>""",
            unsafe_allow_html=True)
    with kc4:
        above_count = sum(1 for p in walk_positions if p.elevation > 0)
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">日照切片 / 總切片</div>
            <div class="metric-value">{above_count}<span class="metric-unit"> / {len(walk_positions)}</span></div>
            <div style="color:#8892b0;font-size:.8rem;margin-top:4px">
                間隔 {interval} min，共 {total_walk} min</div></div>""",
            unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col_left, col_right = st.columns([3, 2], gap="large")

    with col_left:
        # 高度角折線
        st.markdown('<p class="section-title">📈 步行期間太陽高度角</p>', unsafe_allow_html=True)
        fig_elev = go.Figure()
        fig_elev.add_hline(y=0, line_dash="dash", line_color="#555",
                           annotation_text="地平線 0°", annotation_font_color="#777")
        fig_elev.add_trace(go.Scatter(
            x=walk_df["時間(本地)"], y=walk_df["高度角(°)"],
            mode="lines+markers", name="高度角",
            line=dict(color="#64ffda", width=3),
            marker=dict(size=8, color="#64ffda", line=dict(color="#0f1117", width=2)),
            fill="tozeroy", fillcolor="rgba(100,255,218,0.08)",
            hovertemplate="時間：%{x}<br>高度角：%{y:.2f}°<extra></extra>",
        ))
        fig_elev.add_trace(go.Scatter(
            x=[walk_df["時間(本地)"].iloc[0]], y=[walk_df["高度角(°)"].iloc[0]],
            mode="markers", name="出發點",
            marker=dict(size=14, color="#ff6b6b", symbol="star",
                        line=dict(color="#fff", width=1)),
        ))
        fig_elev.update_layout(
            height=300, paper_bgcolor="#0f1117", plot_bgcolor="#13161f",
            font=dict(color="#ccd6f6", size=12),
            legend=dict(orientation="h", y=1.08),
            xaxis=dict(title="本地時間", gridcolor="#1e2130"),
            yaxis=dict(title="高度角 (°)", gridcolor="#1e2130"),
            margin=dict(l=10, r=10, t=10, b=10),
        )
        st.plotly_chart(fig_elev, use_container_width=True)

        # 方位角折線
        st.markdown('<p class="section-title">🧭 步行期間太陽方位角</p>', unsafe_allow_html=True)
        fig_az = go.Figure()
        for angle, label in [(0,"北N"),(90,"東E"),(180,"南S"),(270,"西W")]:
            fig_az.add_hline(y=angle, line_dash="dot", line_color="#2a3050",
                             annotation_text=label, annotation_font_color="#556")
        fig_az.add_trace(go.Scatter(
            x=walk_df["時間(本地)"], y=walk_df["方位角(°)"],
            mode="lines+markers", name="方位角",
            line=dict(color="#f7c85b", width=3),
            marker=dict(size=8, color="#f7c85b", line=dict(color="#0f1117", width=2)),
            hovertemplate="時間：%{x}<br>方位角：%{y:.2f}°<extra></extra>",
        ))
        fig_az.add_trace(go.Scatter(
            x=[walk_df["時間(本地)"].iloc[0]], y=[walk_df["方位角(°)"].iloc[0]],
            mode="markers", name="出發點",
            marker=dict(size=14, color="#ff6b6b", symbol="star",
                        line=dict(color="#fff", width=1)),
        ))
        fig_az.update_layout(
            height=270, paper_bgcolor="#0f1117", plot_bgcolor="#13161f",
            font=dict(color="#ccd6f6", size=12),
            legend=dict(orientation="h", y=1.08),
            xaxis=dict(title="本地時間", gridcolor="#1e2130"),
            yaxis=dict(title="方位角 (°)", gridcolor="#1e2130", range=[0, 360],
                       tickvals=[0,90,180,270,360],
                       ticktext=["北0°","東90°","南180°","西270°","360°"]),
            margin=dict(l=10, r=10, t=10, b=10),
        )
        st.plotly_chart(fig_az, use_container_width=True)

    with col_right:
        # 羅盤
        st.markdown('<p class="section-title">🧭 太陽方位角羅盤</p>', unsafe_allow_html=True)
        compass = go.Figure()
        compass.add_trace(go.Scatterpolar(
            r=[1]*16, theta=[i*22.5 for i in range(16)],
            mode="markers", marker=dict(size=4, color="#2a3050"),
            showlegend=False, hoverinfo="skip",
        ))
        compass.add_trace(go.Scatterpolar(
            r=[0, 0.85], theta=[current_pos.azimuth]*2,
            mode="lines+markers", name=f"T+0  {current_pos.azimuth:.1f}°",
            line=dict(color="#ff6b6b", width=4),
            marker=dict(size=[0, 14], color="#ff6b6b"),
        ))
        for i, pos in enumerate(walk_positions[1:], 1):
            alpha = 0.3 + 0.5*(i/len(walk_positions))
            compass.add_trace(go.Scatterpolar(
                r=[0, 0.7], theta=[pos.azimuth]*2,
                mode="lines",
                name=f"T+{pos.offset_minutes}min  {pos.azimuth:.1f}°",
                line=dict(color=f"rgba(100,255,218,{alpha:.2f})", width=2),
            ))
        compass.update_layout(
            height=360, paper_bgcolor="#0f1117",
            polar=dict(
                bgcolor="#13161f",
                angularaxis=dict(
                    tickmode="array",
                    tickvals=[0,45,90,135,180,225,270,315],
                    ticktext=["北N","NE","東E","SE","南S","SW","西W","NW"],
                    direction="clockwise", rotation=90,
                    color="#8892b0", gridcolor="#1e2130",
                ),
                radialaxis=dict(visible=False, range=[0, 1]),
            ),
            font=dict(color="#ccd6f6", size=11),
            legend=dict(font=dict(size=10), bgcolor="#0f1117", x=1.05),
            margin=dict(l=0, r=80, t=10, b=10),
        )
        st.plotly_chart(compass, use_container_width=True)

        if show_full_day and not full_df.empty:
            st.markdown('<p class="section-title">🌅 全日高度角軌跡</p>', unsafe_allow_html=True)
            fig_fd = go.Figure()
            above_fd = full_df[full_df["在地平線上"]]
            below_fd = full_df[~full_df["在地平線上"]]
            fig_fd.add_trace(go.Scatter(
                x=below_fd["時間(本地)"], y=below_fd["高度角(°)"],
                mode="lines", name="地平線以下", line=dict(color="#334", width=2)))
            fig_fd.add_trace(go.Scatter(
                x=above_fd["時間(本地)"], y=above_fd["高度角(°)"],
                mode="lines", name="日照時段", line=dict(color="#f7c85b", width=2),
                fill="tozeroy", fillcolor="rgba(247,200,91,0.12)"))
            if len(walk_df) >= 2:
                fig_fd.add_vrect(
                    x0=walk_df["時間(本地)"].iloc[0],
                    x1=walk_df["時間(本地)"].iloc[-1],
                    fillcolor="rgba(100,255,218,0.07)",
                    line_width=1, line_color="#64ffda",
                    annotation_text="步行窗口",
                    annotation_font_color="#64ffda", annotation_font_size=11,
                )
            fig_fd.add_hline(y=0, line_dash="dash", line_color="#444")
            fig_fd.update_layout(
                height=210, paper_bgcolor="#0f1117", plot_bgcolor="#13161f",
                font=dict(color="#ccd6f6", size=11),
                legend=dict(orientation="h", y=1.1, font=dict(size=10)),
                xaxis=dict(title="時間", gridcolor="#1e2130",
                           tickmode="linear", dtick=24),
                yaxis=dict(title="高度角(°)", gridcolor="#1e2130"),
                margin=dict(l=5, r=5, t=5, b=5),
            )
            st.plotly_chart(fig_fd, use_container_width=True)

    # 大安區地圖 + 太陽方位射線
    st.divider()
    st.markdown('<p class="section-title">🗺️ 大安區地圖｜太陽方位方向射線</p>',
                unsafe_allow_html=True)
    mc1, mc2 = st.columns([3, 2], gap="large")

    with mc1:
        m1 = folium.Map(location=list(DAAN_CENTER), zoom_start=15,
                        tiles="CartoDB dark_matter")
        m1.fit_bounds(DAAN_BOUNDS)
        folium.Rectangle(
            bounds=DAAN_BOUNDS, color="#64ffda", weight=1.5,
            fill=True, fill_color="#64ffda", fill_opacity=0.03,
            tooltip="大安區研究範圍",
        ).add_to(m1)
        folium.Marker(
            list(DAAN_CENTER), tooltip="大安區中心",
            icon=folium.Icon(color="red", icon="map-marker", prefix="fa"),
        ).add_to(m1)
        palette_map = ["#ff6b6b","#64ffda","#f7c85b","#a29bfe","#fd79a8","#00cec9"]
        for i, pos in enumerate(walk_positions):
            az_r = math.radians(pos.azimuth)
            end_lat = lat + 0.008 * math.cos(az_r)
            end_lon = lon + 0.008 * math.sin(az_r)
            c = palette_map[i % len(palette_map)]
            folium.PolyLine(
                [[lat, lon], [end_lat, end_lon]], color=c,
                weight=4 if i == 0 else 2,
                dash_array=None if i == 0 else "5 3",
                tooltip=f"T+{pos.offset_minutes}min | Az {pos.azimuth:.1f}° | El {pos.elevation:.1f}°",
            ).add_to(m1)
            folium.CircleMarker(
                [end_lat, end_lon], radius=5, color=c,
                fill=True, fill_color=c, fill_opacity=0.9,
                tooltip=f"T+{pos.offset_minutes}min ☀️{pos.elevation:.1f}° → {pos.azimuth:.1f}°",
            ).add_to(m1)
        st_folium(m1, height=420, use_container_width=True)

    with mc2:
        st.markdown('<p class="section-title">📋 時間分片計算結果</p>', unsafe_allow_html=True)
        disp = walk_df[["時間(本地)","offset_min","高度角(°)","方位角(°)","在地平線上"]].copy()
        disp.columns = ["本地時間","T+(min)","高度角°","方位角°","日照"]
        disp["日照"] = disp["日照"].map({True: "☀️ 是", False: "🌙 否"})
        st.dataframe(
            disp.style
                .format({"高度角°":"{:+.2f}","方位角°":"{:.2f}"})
                .map(lambda v: "color:#64ffda" if "☀️" in str(v) else "color:#ff6b6b",
                     subset=["日照"])
                .set_properties(**{"background-color":"#13161f","color":"#ccd6f6",
                                   "border-color":"#1e2130"}),
            use_container_width=True, height=360,
        )
        st.divider()
        ev = walk_df["高度角(°)"]
        s1, s2 = st.columns(2)
        s1.metric("最大高度角", f"{ev.max():+.2f}°")
        s2.metric("最小高度角", f"{ev.min():+.2f}°")
        s1.metric("日照切片數",
                  f"{sum(1 for p in walk_positions if p.elevation>0)} / {len(walk_positions)}")
        s2.metric("平均高度角", f"{ev.mean():+.2f}°")
        st.metric("方位角偏移量（步行期間）",
                  f"{walk_df['方位角(°)'].max() - walk_df['方位角(°)'].min():.2f}°")


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  TAB 2 — Shadow Casting Engine                                           ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
with tab2:
    st.divider()
    st.markdown('<p class="section-title">🏙️ 大安區建物動態陰影投影 (Task 2)</p>',
                unsafe_allow_html=True)

    ctrl1, ctrl2, ctrl3 = st.columns([2, 2, 1])
    with ctrl1:
        selected_offset = st.select_slider(
            "選擇時間切片 (T+ 分鐘)",
            options=[p.offset_minutes + 1 for p in walk_positions],
            value=1,
        )
    with ctrl2:
        show_union     = st.toggle("顯示 Unary Union 總遮罩", value=True)
        show_buildings = st.toggle("顯示建物底圖", value=True)
    with ctrl3:
        st.markdown("<br>", unsafe_allow_html=True)
        run_btn = st.button("🔄 計算陰影", type="primary", use_container_width=True)

    @st.cache_resource(show_spinner="載入大安區建物資料...")
    def get_buildings():
        return load_buildings()

    @st.cache_resource
    def get_buildings_wgs84():
        return get_buildings().to_crs("EPSG:4326")

    cache_key = (
        departure_local.isoformat(),
        interval,
        total_walk,
        selected_offset,
        show_union,
    )

    if "shadow_results_cache" not in st.session_state:
        st.session_state["shadow_results_cache"] = {}

    if run_btn or cache_key not in st.session_state["shadow_results_cache"]:
        with st.spinner("計算動態陰影中，請稍候..."):
            bld = get_buildings()
            selected_pos = next(
                (p for p in walk_positions if p.offset_minutes + 1 == selected_offset),
                walk_positions[0],
            )
            sel_result: ShadowResult = compute_shadow_polygons(
                selected_pos,
                buildings=bld,
                build_union=show_union,
            )
        st.session_state["shadow_results_cache"][cache_key] = sel_result

    sel_result: ShadowResult = st.session_state["shadow_results_cache"][cache_key]
    results: list[ShadowResult] = [sel_result]

    sel_pos = sel_result.solar_position

    sk1, sk2, sk3, sk4 = st.columns(4)
    with sk1:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">太陽高度角</div>
            <div class="metric-value">{sel_pos.elevation:+.2f}<span class="metric-unit">°</span></div>
            </div>""", unsafe_allow_html=True)
    with sk2:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">太陽方位角</div>
            <div class="metric-value">{sel_pos.azimuth:.2f}<span class="metric-unit">°</span></div>
            </div>""", unsafe_allow_html=True)
    with sk3:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">投影建物數</div>
            <div class="metric-value">{sel_result.n_buildings_shadow:,}
                <span class="metric-unit"> 棠</span></div></div>""",
            unsafe_allow_html=True)
    with sk4:
        st.markdown(f"""<div class="metric-card">
            <div class="metric-label">平均陰影長度</div>
            <div class="metric-value">{sel_result.mean_shadow_length_m:.1f}
                <span class="metric-unit"> m</span></div></div>""",
            unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    map2_col, stat_col = st.columns([3, 2], gap="large")

    with map2_col:
        local_t_label = (sel_pos.time.astimezone(tz)).strftime("%H:%M")
        st.markdown(
            f'<p class="section-title">🗺️ 陰影地圖｜'
            f'T+{selected_offset}min（{local_t_label}）</p>',
            unsafe_allow_html=True,
        )
        m2 = folium.Map(tiles="CartoDB dark_matter")
        m2.fit_bounds(DAAN_BOUNDS)

        if show_buildings:
            bld_wgs = get_buildings_wgs84()
            folium.GeoJson(
                bld_wgs.__geo_interface__,
                name="建物底圖",
                style_function=lambda _: {
                    "fillColor": "#ff0000",
                    "fillOpacity": 0.0,
                    "color": "#ff4444",
                    "weight": 1.5,
                    "dashArray": "5 4",
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=["BUILD_ID","BUILD_H"],
                    aliases=["建物ID","高度(m)"],
                ),
            ).add_to(m2)

        if not sel_result.shadow_gdf.empty and not show_union:
            folium.GeoJson(
                sel_result.shadow_gdf.__geo_interface__,
                name="建物陰影",
                style_function=lambda _: {
                    "fillColor": "#263238", "color": "#546e7a",
                    "weight": 0.3, "fillOpacity": 0.55,
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=["BUILD_ID","BUILD_H","shadow_len"],
                    aliases=["建物ID","高度(m)","陰影長(m)"],
                ),
            ).add_to(m2)

        if show_union and not sel_result.union_polygon.empty:
            folium.GeoJson(
                sel_result.union_polygon.__geo_interface__,
                name="總陰影遮罩",
                style_function=lambda _: {
                    "fillColor": "#1a237e", "color": "#7986cb",
                    "weight": 0.8, "fillOpacity": 0.50,
                },
                tooltip="Unary Union 總陰影遮罩",
            ).add_to(m2)

        az_r = math.radians(sel_pos.azimuth)
        sun_lat = DAAN_CENTER[0] + 0.012 * math.cos(az_r)
        sun_lon = DAAN_CENTER[1] + 0.012 * math.sin(az_r)
        folium.PolyLine(
            [list(DAAN_CENTER), [sun_lat, sun_lon]],
            color="#FFD600", weight=3, dash_array="8 4",
            tooltip=f"太陽方向 {sel_pos.azimuth:.1f}°",
        ).add_to(m2)
        folium.Marker(
            [sun_lat, sun_lon],
            icon=folium.DivIcon(
                html='<div style="font-size:22px;color:#FFD600;'
                     'text-shadow:0 0 4px #000">☀️</div>'
            ),
            tooltip=f"太陽方位 {sel_pos.azimuth:.1f}° | 高度角 {sel_pos.elevation:.1f}°",
        ).add_to(m2)

        folium.LayerControl(collapsed=False).add_to(m2)
        st_folium(m2, center=list(DAAN_CENTER), zoom=15, height=520, use_container_width=True)

    with stat_col:
        st.markdown('<p class="section-title">📊 各時刻陰影統計對比</p>',
                    unsafe_allow_html=True)
        stats_rows = []
        for r in results:
            lt = (r.solar_position.time.astimezone(tz)).strftime("%H:%M")
            stats_rows.append({
                "時間":          lt,
                "T+(min)":      r.solar_position.offset_minutes + 1,
                "高度角°":      round(r.solar_position.elevation, 2),
                "方位角°":      round(r.solar_position.azimuth, 2),
                "投影棟數":     r.n_buildings_shadow,
                "平均陰影長(m)": round(r.mean_shadow_length_m, 1),
            })
        stats_df = pd.DataFrame(stats_rows)

        def highlight_sel(row):
            s = "background-color:#1a3a2a;color:#64ffda"
            return [s if row["T+(min)"] == selected_offset else ""]*len(row)

        st.dataframe(
            stats_df.style
                .apply(highlight_sel, axis=1)
                .format({"高度角°":"{:+.2f}","方位角°":"{:.2f}"})
                .set_properties(**{"background-color":"#13161f","color":"#ccd6f6",
                                   "border-color":"#1e2130"}),
            use_container_width=True, height=260,
        )

        st.markdown('<p class="section-title">📉 平均陰影長度隨時間變化</p>',
                    unsafe_allow_html=True)
        bar_colors = [
            "#64ffda" if row["T+(min)"] == selected_offset else "#2a5a4a"
            for _, row in stats_df.iterrows()
        ]
        fig_bar = go.Figure(go.Bar(
            x=stats_df["時間"], y=stats_df["平均陰影長(m)"],
            marker_color=bar_colors,
            text=stats_df["平均陰影長(m)"].apply(lambda v: f"{v:.0f}m"),
            textposition="outside",
            hovertemplate="時間：%{x}<br>平均陰影長：%{y:.1f} m<extra></extra>",
        ))
        fig_bar.update_layout(
            height=200, paper_bgcolor="#0f1117", plot_bgcolor="#13161f",
            font=dict(color="#ccd6f6", size=11),
            xaxis=dict(gridcolor="#1e2130"),
            yaxis=dict(title="公尺(m)", gridcolor="#1e2130"),
            margin=dict(l=5, r=5, t=5, b=5),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        st.markdown('<p class="section-title">📐 陰影計算公式</p>', unsafe_allow_html=True)
        st.latex(r"L = \frac{H}{\tan(\theta)}")
        st.markdown("""
| 符號 | 說明 |
|------|------|
| $L$ | 陰影長度（公尺） |
| $H$ | 建物高度 `BUILD_H`（公尺） |
| $\\theta$ | 太陽高度角（弧度） |

**陰影方向**：方位角 + 180°（反向投射）  
**Unary Union**：合併重疊陰影 → 總遮罩  
**座標**：計算於 EPSG:3826（公尺），輸出為 EPSG:4326
    """)

    st.divider()
    st.markdown('<p class="section-title">📈 全時段：投影建物數趨勢</p>',
                unsafe_allow_html=True)
    fig_trend = go.Figure(go.Scatter(
        x=stats_df["時間"], y=stats_df["投影棟數"],
        mode="lines+markers+text",
        line=dict(color="#64ffda", width=2),
        marker=dict(size=9, color=[
            "#ff6b6b" if t == selected_offset else "#64ffda"
            for t in stats_df["T+(min)"]
        ]),
        text=stats_df["投影棟數"], textposition="top center",
        hovertemplate="時間：%{x}<br>投影棟數：%{y}<extra></extra>",
    ))
    fig_trend.update_layout(
        height=180, paper_bgcolor="#0f1117", plot_bgcolor="#13161f",
        font=dict(color="#ccd6f6", size=12),
        xaxis=dict(title="本地時間", gridcolor="#1e2130"),
        yaxis=dict(title="棟數", gridcolor="#1e2130"),
        margin=dict(l=10, r=10, t=10, b=10),
    )
    st.plotly_chart(fig_trend, use_container_width=True)

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  TAB 3 — Air Quality Spatial Distribution (MOENV API)                    ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
with tab3:
    st.divider()
    st.markdown('<p class="section-title">🌫️ 空氣品質空間分布｜大安區周邊測站</p>',
                unsafe_allow_html=True)

    # ── 取得氣象資料（帶 session 快取）──────────────────────────────────────
    if "weather" not in st.session_state:
        with st.spinner("正在串接氣象與空品資料..."):
            try:
                st.session_state["weather"] = fetch_weather()
                st.session_state["weather_error"] = None
            except Exception as e:
                st.session_state["weather_error"] = str(e)

    if st.session_state.get("weather_error"):
        st.error(f"⚠️ API 串接失敗：{st.session_state['weather_error']}")
        st.stop()

    w: WeatherData = st.session_state["weather"]

    # ── KPI 卡片列 1：大安區空品概況 ───────────────────────────────────────────
    st.markdown('<p class="section-title">📍 大安區空品概況（Kriging 平滑）</p>',
                unsafe_allow_html=True)
    aqk1, aqk2, aqk3, aqk4 = st.columns(4)

    def _aqcard(col, label, value, unit, sub="", color="#64ffda"):
        col.markdown(f"""<div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value" style="color:{color}">{value}<span class="metric-unit">{unit}</span></div>
            <div style="color:#8892b0;font-size:.78rem;margin-top:4px">{sub}</div>
            </div>""", unsafe_allow_html=True)

    pm25_kriging_display = f"{w.pm25_kriging:.1f}" if w.pm25_kriging is not None else "N/A"
    _aqcard(aqk1, "PM2.5（Kriging）", pm25_kriging_display, " μg/m³",
            f"{w.pm25_method}｜{w.pm25_neighbor_count} 站", w.pm25_color)
    _aqcard(aqk2, "PM2.5 等級", w.pm25_level, "",
            "基於 Kriging 平滑值", w.pm25_color)
    _aqcard(aqk3, "最近測站 AQI", f"{w.aqi}" if w.aqi else "N/A", "",
            w.aqi_site_name, w.aqi_color)
    _aqcard(aqk4, "AQI 狀態", w.aqi_status or "Unavailable", "",
            w.aqi_pollutant or "主要污染物未提供", w.aqi_color)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 空間地圖：測站分布 ───────────────────────────────────────────────────
    aq_map_col, aq_table_col = st.columns([3, 2], gap="large")

    with aq_map_col:
        st.markdown('<p class="section-title">🗺️ 空品測站空間分布｜PM2.5 熱力圖</p>',
                    unsafe_allow_html=True)

        # 初始化地圖 (移除原本的 location, zoom_start 與 fit_bounds，統一交由 st_folium 控制)
        m3 = folium.Map(tiles="CartoDB dark_matter")

        # 大安區範圍
        folium.Rectangle(
            bounds=DAAN_BOUNDS, color="#64ffda", weight=2,
            fill=True, fill_color="#64ffda", fill_opacity=0.05,
            tooltip="大安區研究範圍",
        ).add_to(m3)

        # 大安區中心點
        folium.Marker(
            list(DAAN_CENTER), tooltip="大安區中心",
            icon=folium.Icon(color="blue", icon="map-marker", prefix="fa"),
        ).add_to(m3)

        # 繪製所有附近測站
        if w.nearby_stations:
            for station in w.nearby_stations:
                if station.pm25 is None:
                    continue

                # 根據 PM2.5 等級決定顏色
                if station.pm25 <= 15.4:
                    color = "#4caf50"  # Good
                elif station.pm25 <= 35.4:
                    color = "#ffeb3b"  # Moderate
                elif station.pm25 <= 54.4:
                    color = "#ff9800"  # Unhealthy SG
                elif station.pm25 <= 150.4:
                    color = "#f44336"  # Unhealthy
                else:
                    color = "#8e24aa"  # Very Unhealthy

                # 計算距離大安區中心的距離
                dist_km = _haversine_m(
                    DAAN_CENTER[0], DAAN_CENTER[1],
                    station.latitude, station.longitude
                ) / 1000.0

                folium.CircleMarker(
                    [station.latitude, station.longitude],
                    radius=8 + min(station.pm25 / 5, 12),
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.7,
                    tooltip=f"""
                    <b>{station.site_name}</b><br>
                    PM2.5: {station.pm25:.1f} μg/m³<br>
                    AQI: {station.aqi if station.aqi else 'N/A'}<br>
                    距離: {dist_km:.1f} km<br>
                    縣市: {station.county}
                    """,
                ).add_to(m3)

                folium.Marker(
                    [station.latitude, station.longitude],
                    icon=folium.DivIcon(
                        html=f'<div style="font-size:10px;color:#fff;'
                             f'background:{color};border-radius:50%;'
                             f'width:20px;height:20px;display:flex;'
                             f'align-items:center;justify-content:center;'
                             f'border:2px solid #fff">{station.pm25:.0f}</div>'
                    ),
                    tooltip=station.site_name,
                ).add_to(m3)

        folium.LayerControl(collapsed=False).add_to(m3)
        
        # ✅ 關鍵修改：在此處使用 center 和 zoom 強制鎖定 st_folium 的渲染視角
        st_folium(
            m3, 
            center=list(DAAN_CENTER), 
            zoom=14, 
            height=500, 
            use_container_width=True
        )

    with aq_table_col:
        st.markdown('<p class="section-title">📋 測站比較表</p>',
                    unsafe_allow_html=True)

        if w.nearby_stations:
            station_data = []
            for station in w.nearby_stations:
                if station.pm25 is None:
                    continue

                dist_km = _haversine_m(
                    DAAN_CENTER[0], DAAN_CENTER[1],
                    station.latitude, station.longitude
                ) / 1000.0

                # PM2.5 等級
                if station.pm25 <= 15.4:
                    level = "良好"
                    level_color = "#4caf50"
                elif station.pm25 <= 35.4:
                    level = "普通"
                    level_color = "#ffeb3b"
                elif station.pm25 <= 54.4:
                    level = "對敏感群不健康"
                    level_color = "#ff9800"
                elif station.pm25 <= 150.4:
                    level = "對所有族群不健康"
                    level_color = "#f44336"
                else:
                    level = "非常不健康"
                    level_color = "#8e24aa"

                station_data.append({
                    "測站名稱": station.site_name,
                    "縣市": station.county,
                    "PM2.5": station.pm25,
                    "AQI": station.aqi if station.aqi else None,
                    "等級": level,
                    "距離(km)": dist_km,
                })

            if station_data:
                df_stations = pd.DataFrame(station_data)
                st.dataframe(
                    df_stations.style
                        .format({"PM2.5": "{:.1f}", "距離(km)": "{:.1f}"})
                        .set_properties(**{"background-color":"#13161f","color":"#ccd6f6",
                                           "border-color":"#1e2130"}),
                    use_container_width=True, height=400,
                )
            else:
                st.warning("無可用的測站資料")
        else:
            st.warning("無法取得測站資料")

        st.markdown('<p class="section-title">📊 PM2.5 分布統計</p>',
                    unsafe_allow_html=True)

        if w.nearby_stations:
            pm25_values = [s.pm25 for s in w.nearby_stations if s.pm25 is not None]
            if pm25_values:
                import numpy as np
                s1, s2, s3, s4 = st.columns(4)
                s1.metric("平均 PM2.5", f"{np.mean(pm25_values):.1f} μg/m³")
                s2.metric("最大 PM2.5", f"{np.max(pm25_values):.1f} μg/m³")
                s3.metric("最小 PM2.5", f"{np.min(pm25_values):.1f} μg/m³")
                s4.metric("測站數量", f"{len(pm25_values)}")

    st.divider()
    st.markdown('<p class="section-title">📈 PM2.5 距離分布圖</p>',
                unsafe_allow_html=True)

    if w.nearby_stations:
        station_data = []
        for station in w.nearby_stations:
            if station.pm25 is None:
                continue
            dist_km = _haversine_m(
                DAAN_CENTER[0], DAAN_CENTER[1],
                station.latitude, station.longitude
            ) / 1000.0
            station_data.append({
                "距離(km)": dist_km,
                "PM2.5": station.pm25,
                "測站": station.site_name,
            })

        if station_data:
            df_scatter = pd.DataFrame(station_data)
            fig_scatter = go.Figure(go.Scatter(
                x=df_scatter["距離(km)"],
                y=df_scatter["PM2.5"],
                mode="markers+text",
                marker=dict(
                    size=df_scatter["PM2.5"] * 0.8,
                    color=df_scatter["PM2.5"],
                    colorscale="RdYlGn_r",
                    showscale=True,
                    colorbar=dict(title="PM2.5 (μg/m³)", x=1.02),
                ),
                text=df_scatter["測站"],
                textposition="top center",
                textfont=dict(size=9, color="#ccd6f6"),
                hovertemplate="測站：%{text}<br>距離：%{x:.1f} km<br>PM2.5：%{y:.1f} μg/m³<extra></extra>",
            ))
            fig_scatter.update_layout(
                height=300, paper_bgcolor="#0f1117", plot_bgcolor="#13161f",
                font=dict(color="#ccd6f6"),
                xaxis=dict(title="距離大安區中心 (km)", gridcolor="#1e2130"),
                yaxis=dict(title="PM2.5 (μg/m³)", gridcolor="#1e2130"),
                margin=dict(l=10, r=120, t=10, b=10),
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  TAB 4 — Real-time Weather & Microclimate (CWA API)                      ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
with tab4:
    st.divider()
    st.markdown('<p class="section-title">🌡️ 即時氣象介接｜臺北站（中央氣象署 CWA）</p>',
                unsafe_allow_html=True)

    # ── 取得氣象資料（帶 session 快取，避免每次 rerun 重複呼叫）──────────────
    w4c1, w4c2 = st.columns([4, 1])
    with w4c2:
        st.markdown("<br>", unsafe_allow_html=True)
        refresh_btn = st.button("🔄 刷新氣象", type="primary", use_container_width=True)

    if "weather" not in st.session_state or refresh_btn:
        with st.spinner("正在串接 CWA 氣象資料..."):
            try:
                st.session_state["weather"] = fetch_weather()
                st.session_state["weather_error"] = None
            except Exception as e:
                st.session_state["weather_error"] = str(e)

    if st.session_state.get("weather_error"):
        st.error(f"⚠️ API 串接失敗：{st.session_state['weather_error']}")
        st.stop()

    w: WeatherData = st.session_state["weather"]
    aqi_display = f"{w.aqi}" if w.aqi is not None else "N/A"
    pm25_display = f"{w.pm25:.1f}" if w.pm25 is not None else "N/A"
    pm25_kriging_display = f"{w.pm25_kriging:.1f}" if w.pm25_kriging is not None else "N/A"

    with w4c1:
        st.markdown(
            f"<span style='color:#8892b0;font-size:.9rem;'>"
            f"臺北站（StationID: 466920）｜觀測時間：{w.obs_time}｜"
            f"UV 資料日期：{w.uv_date}"
            f"{'｜空品更新：' + w.air_quality_time if w.air_quality_time else ''}</span>",
            unsafe_allow_html=True,
        )

    # ── KPI 卡片列 1：基本觀測 ───────────────────────────────────────────────
    st.markdown('<p class="section-title">🔭 即時觀測數據</p>', unsafe_allow_html=True)
    wk1, wk2, wk3, wk4, wk5 = st.columns(5)

    def _wcard(col, label, value, unit, sub=""):
        col.markdown(f"""<div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}<span class="metric-unit">{unit}</span></div>
            <div style="color:#8892b0;font-size:.78rem;margin-top:4px">{sub}</div>
            </div>""", unsafe_allow_html=True)

    _wcard(wk1, "氣溫 Temperature", f"{w.temperature:.1f}", " °C", w.weather_desc)
    _wcard(wk2, "相對濕度 Humidity", f"{w.humidity}", " %", "")
    _wcard(wk3, "風速 Wind Speed",   f"{w.wind_speed:.1f}", " m/s", f"風向 {w.wind_direction:.0f}°")
    _wcard(wk4, "降雨量 Precipitation", f"{w.precipitation:.1f}", " mm", "當前小時累計")
    _wcard(wk5, "天氣預報", w.forecast_weather[:6], "",
           f"降雨機率 {w.forecast_pop}%")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── KPI 卡片列 2：衍生指標 ───────────────────────────────────────────────
    st.markdown('<p class="section-title">🧮 衍生微氣候指標</p>', unsafe_allow_html=True)
    di1, di2, di3, di4 = st.columns(4)

    # 體感溫度
    di1.markdown(f"""<div class="metric-card">
        <div class="metric-label">體感溫度 Apparent Temp</div>
        <div class="metric-value">{w.apparent_temp:.1f}<span class="metric-unit"> °C</span></div>
        <div style="color:#8892b0;font-size:.78rem;margin-top:4px">Steadman 公式</div>
        </div>""", unsafe_allow_html=True)

    # 熱指數
    di2.markdown(f"""<div class="metric-card">
        <div class="metric-label">熱指數 Heat Index</div>
        <div class="metric-value">{w.heat_index:.1f}<span class="metric-unit"> °C</span></div>
        <div style="color:#8892b0;font-size:.78rem;margin-top:4px">Rothfusz 迴歸</div>
        </div>""", unsafe_allow_html=True)

    # WBGT
    di3.markdown(f"""<div class="metric-card">
        <div class="metric-label">WBGT 濕球黑球溫度</div>
        <div class="metric-value">{w.wbgt:.1f}<span class="metric-unit"> °C</span></div>
        <div style="background:{w.heat_risk_color};color:#000;border-radius:5px;
             padding:2px 6px;font-size:.78rem;display:inline-block;margin-top:4px">
             {w.heat_risk}</div>
        </div>""", unsafe_allow_html=True)

    # 陰影加權倍率
    di4.markdown(f"""<div class="metric-card">
        <div class="metric-label">陰影加權倍率</div>
        <div class="metric-value">{w.shadow_weight_multiplier:.2f}<span class="metric-unit"> ×</span></div>
        <div style="color:#8892b0;font-size:.78rem;margin-top:4px">UV + WBGT 綜合計算</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── AQI / PM2.5 區塊 ────────────────────────────────────────────────────
    st.markdown('<p class="section-title">🌫️ 空氣品質｜最近測站 + Kriging 平滑 PM2.5</p>',
                unsafe_allow_html=True)
    aq1, aq2, aq3, aq4 = st.columns(4)

    aq1.markdown(f"""<div class="metric-card">
        <div class="metric-label">AQI｜最近測站</div>
        <div class="metric-value">{aqi_display}<span class="metric-unit"></span></div>
        <div style="background:{w.aqi_color};color:#000;border-radius:5px;
             padding:2px 6px;font-size:.78rem;display:inline-block;margin-top:4px">
             {w.aqi_status or 'Unavailable'}</div>
        </div>""", unsafe_allow_html=True)

    aq2.markdown(f"""<div class="metric-card">
        <div class="metric-label">PM2.5｜最近測站</div>
        <div class="metric-value">{pm25_display}<span class="metric-unit"> μg/m³</span></div>
        <div style="color:#8892b0;font-size:.78rem;margin-top:4px">{w.aqi_site_name or '無測站資料'}</div>
        </div>""", unsafe_allow_html=True)

    aq3.markdown(f"""<div class="metric-card">
        <div class="metric-label">PM2.5｜Kriging</div>
        <div class="metric-value">{pm25_kriging_display}<span class="metric-unit"> μg/m³</span></div>
        <div style="color:#8892b0;font-size:.78rem;margin-top:4px">{w.pm25_method or 'Unavailable'}｜{w.pm25_neighbor_count} 站</div>
        </div>""", unsafe_allow_html=True)

    aq4.markdown(f"""<div class="metric-card">
        <div class="metric-label">PM2.5 等級</div>
        <div class="metric-value" style="color:{w.pm25_color}">{w.pm25_level}</div>
        <div style="color:#8892b0;font-size:.78rem;margin-top:4px">{w.aqi_pollutant or '主要污染物未提供'}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    aq_chart_col, aq_info_col = st.columns([2, 3], gap="large")

    with aq_chart_col:
        fig_aqi = go.Figure(go.Indicator(
            mode="gauge+number",
            value=w.aqi if w.aqi is not None else 0,
            title={"text": f"AQI｜{w.aqi_site_name or '最近測站'}",
                   "font": {"color": "#ccd6f6", "size": 14}},
            gauge={
                "axis": {"range": [0, 300], "tickcolor": "#8892b0",
                         "tickfont": {"color": "#8892b0"}},
                "bar": {"color": w.aqi_color, "thickness": 0.3},
                "bgcolor": "#13161f",
                "bordercolor": "#3a4060",
                "steps": [
                    {"range": [0, 50], "color": "#1b3a1b"},
                    {"range": [50, 100], "color": "#3a3a00"},
                    {"range": [100, 150], "color": "#3a2000"},
                    {"range": [150, 200], "color": "#3a0000"},
                    {"range": [200, 300], "color": "#2a0033"},
                ],
            },
            number={"font": {"color": w.aqi_color, "size": 44}},
        ))
        fig_aqi.update_layout(
            height=260, paper_bgcolor="#0f1117",
            font=dict(color="#ccd6f6"),
            margin=dict(l=20, r=20, t=40, b=10),
        )
        st.plotly_chart(fig_aqi, use_container_width=True)

    with aq_info_col:
        st.markdown("""
<div style="background:#13161f;border:1px solid #3a4060;border-radius:10px;padding:16px 20px;">
<table style="width:100%;border-collapse:collapse;color:#ccd6f6;font-size:.9rem;">
  <tr style="border-bottom:1px solid #3a4060">
    <th style="padding:6px 10px;text-align:left">指標</th>
    <th style="padding:6px 10px;text-align:left">數值</th>
    <th style="padding:6px 10px;text-align:left">說明</th>
  </tr>
  <tr><td>AQI</td><td>{aqi}</td><td>{aqi_status}</td></tr>
  <tr><td>最近站 PM2.5</td><td>{pm25_raw} μg/m³</td><td>{site}</td></tr>
  <tr><td>Kriging PM2.5</td><td>{pm25_kriging} μg/m³</td><td>{method}，使用 {neighbors} 站</td></tr>
  <tr><td>主要污染物</td><td>{pollutant}</td><td>環境部測站回傳欄位</td></tr>
</table>
<div style="margin-top:12px;padding:10px;background:#1e2130;border-radius:8px;
     border-left:3px solid {pm25_color}">
  <span style="color:#8892b0;font-size:.8rem">平滑濃度判讀：</span>
  <span style="color:{pm25_color};font-weight:700;font-size:1rem">{pm25_level}</span>
</div>
</div>""".format(
            aqi=aqi_display,
            aqi_status=w.aqi_status or "Unavailable",
            pm25_raw=pm25_display,
            site=w.aqi_site_name or "無最近站資料",
            pm25_kriging=pm25_kriging_display,
            method=w.pm25_method or "Unavailable",
            neighbors=w.pm25_neighbor_count,
            pollutant=w.aqi_pollutant or "未提供",
            pm25_color=w.pm25_color,
            pm25_level=w.pm25_level,
        ), unsafe_allow_html=True)

    # ── UV 指數視覺化區塊 ────────────────────────────────────────────────────
    st.markdown('<p class="section-title">☀️ UV 紫外線指數｜臺北站當日最大值</p>',
                unsafe_allow_html=True)
    uv_col1, uv_col2 = st.columns([2, 3], gap="large")

    with uv_col1:
        # UV 儀表板（Gauge chart）
        uv_val = max(w.uv_index, 0)
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=uv_val,
            title={"text": "UV Index｜臺北站", "font": {"color": "#ccd6f6", "size": 14}},
            delta={"reference": 3, "increasing": {"color": "#f44336"},
                   "decreasing": {"color": "#4caf50"}},
            gauge={
                "axis": {"range": [0, 14], "tickcolor": "#8892b0",
                         "tickfont": {"color": "#8892b0"}},
                "bar":  {"color": w.uv_color, "thickness": 0.3},
                "bgcolor": "#13161f",
                "bordercolor": "#3a4060",
                "steps": [
                    {"range": [0,  3], "color": "#1b3a1b"},
                    {"range": [3,  6], "color": "#3a3a00"},
                    {"range": [6,  8], "color": "#3a2000"},
                    {"range": [8, 11], "color": "#3a0000"},
                    {"range": [11,14], "color": "#2a0033"},
                ],
                "threshold": {"line": {"color": "#fff", "width": 2},
                              "thickness": 0.8, "value": uv_val},
            },
            number={"font": {"color": w.uv_color, "size": 48}},
        ))
        fig_gauge.update_layout(
            height=280, paper_bgcolor="#0f1117",
            font=dict(color="#ccd6f6"),
            margin=dict(l=20, r=20, t=40, b=10),
        )
        st.plotly_chart(fig_gauge, use_container_width=True)

    with uv_col2:
        # UV 等級說明表
        st.markdown("""
<div style="background:#13161f;border:1px solid #3a4060;border-radius:10px;padding:16px 20px;">
<table style="width:100%;border-collapse:collapse;color:#ccd6f6;font-size:.9rem;">
  <tr style="border-bottom:1px solid #3a4060">
    <th style="padding:6px 10px;text-align:left">UV 指數</th>
    <th style="padding:6px 10px;text-align:left">等級</th>
    <th style="padding:6px 10px;text-align:left">防護建議</th>
  </tr>
  <tr><td>0 – 2</td><td><span style="color:#4caf50">●</span> 低量級</td><td>一般防護即可</td></tr>
  <tr><td>3 – 5</td><td><span style="color:#ffeb3b">●</span> 中量級</td><td>戴帽、塗防曬</td></tr>
  <tr><td>6 – 7</td><td><span style="color:#ff9800">●</span> 高量級</td><td>避免正午外出</td></tr>
  <tr><td>8 – 10</td><td><span style="color:#f44336">●</span> 過量級</td><td>儘量留室內</td></tr>
  <tr><td>11+</td><td><span style="color:#9c27b0">●</span> 危險級</td><td>嚴禁曝曬</td></tr>
</table>
<div style="margin-top:12px;padding:10px;background:#1e2130;border-radius:8px;
     border-left:3px solid {uv_c}">
  <span style="color:#8892b0;font-size:.8rem">目前等級：</span>
  <span style="color:{uv_c};font-weight:700;font-size:1rem">{uv_lv}（UV {uv_val:.1f}）</span>
</div>
</div>""".format(uv_c=w.uv_color, uv_lv=w.uv_level, uv_val=uv_val),
        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── WBGT / 熱危害視覺化 ──────────────────────────────────────────────────
    st.markdown('<p class="section-title">🌡️ WBGT 濕球黑球溫度 & 熱危害等級</p>',
                unsafe_allow_html=True)
    wb1, wb2 = st.columns([2, 3], gap="large")

    with wb1:
        fig_wbgt = go.Figure(go.Indicator(
            mode="gauge+number",
            value=w.wbgt,
            title={"text": "WBGT (°C)", "font": {"color": "#ccd6f6", "size": 14}},
            gauge={
                "axis": {"range": [10, 40], "tickcolor": "#8892b0",
                         "tickfont": {"color": "#8892b0"}},
                "bar":  {"color": w.heat_risk_color, "thickness": 0.3},
                "bgcolor": "#13161f",
                "bordercolor": "#3a4060",
                "steps": [
                    {"range": [10, 25], "color": "#1b3a1b"},
                    {"range": [25, 28], "color": "#3a3a00"},
                    {"range": [28, 31], "color": "#3a2000"},
                    {"range": [31, 35], "color": "#3a0000"},
                    {"range": [35, 40], "color": "#2a0033"},
                ],
            },
            number={"font": {"color": w.heat_risk_color, "size": 48},
                    "suffix": "°C"},
        ))
        fig_wbgt.update_layout(
            height=260, paper_bgcolor="#0f1117",
            font=dict(color="#ccd6f6"),
            margin=dict(l=20, r=20, t=40, b=10),
        )
        st.plotly_chart(fig_wbgt, use_container_width=True)

    with wb2:
        st.markdown("""
<div style="background:#13161f;border:1px solid #3a4060;border-radius:10px;padding:16px 20px;">
<table style="width:100%;border-collapse:collapse;color:#ccd6f6;font-size:.9rem;">
  <tr style="border-bottom:1px solid #3a4060">
    <th style="padding:6px 10px;text-align:left">WBGT (°C)</th>
    <th style="padding:6px 10px;text-align:left">等級</th>
    <th style="padding:6px 10px;text-align:left">活動建議</th>
  </tr>
  <tr><td>&lt; 25</td><td><span style="color:#4caf50">●</span> 安全</td><td>正常活動</td></tr>
  <tr><td>25 – 27</td><td><span style="color:#ffeb3b">●</span> 注意</td><td>適度補水</td></tr>
  <tr><td>28 – 30</td><td><span style="color:#ff9800">●</span> 警戒</td><td>減少激烈活動</td></tr>
  <tr><td>31 – 34</td><td><span style="color:#f44336">●</span> 高度警戒</td><td>停止戶外活動</td></tr>
  <tr><td>≥ 35</td><td><span style="color:#9c27b0">●</span> 危險</td><td>禁止一切活動</td></tr>
</table>
<div style="margin-top:12px;padding:10px;background:#1e2130;border-radius:8px;
     border-left:3px solid {rc}">
  <span style="color:#8892b0;font-size:.8rem">目前等級：</span>
  <span style="color:{rc};font-weight:700;font-size:1rem">{rl}（WBGT {wv:.1f}°C）</span>
</div>
</div>""".format(rc=w.heat_risk_color, rl=w.heat_risk, wv=w.wbgt),
        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 陰影加權倍率說明 + 完整數據表 ───────────────────────────────────────
    st.markdown('<p class="section-title">⚖️ 陰影路徑加權倍率（對路徑演算的影響）</p>',
                unsafe_allow_html=True)
    sw1, sw2 = st.columns([3, 2], gap="large")

    with sw1:
        # 視覺化倍率進度條
        sw_pct = min((w.shadow_weight_multiplier - 1.0) / 2.0, 1.0)
        bar_color = w.uv_color
        st.markdown(f"""
<div style="background:#13161f;border:1px solid #3a4060;border-radius:10px;padding:20px;">
  <div style="color:#8892b0;font-size:.8rem;margin-bottom:8px">
    陰影加權倍率 = 1.0 + UV 貢獻（{min(uv_val/8,1.5):.2f}）+ WBGT 貢獻（{max((w.wbgt-25)/10,0):.2f}）
  </div>
  <div style="font-size:2rem;font-weight:700;color:{bar_color};margin-bottom:12px">
    {w.shadow_weight_multiplier:.2f} ×
  </div>
  <div style="background:#1e2130;border-radius:8px;height:14px;overflow:hidden">
    <div style="background:{bar_color};width:{sw_pct*100:.1f}%;height:100%;
         border-radius:8px;transition:width .5s"></div>
  </div>
  <div style="color:#8892b0;font-size:.78rem;margin-top:8px">
    倍率越高 → 避曬路徑的吸引力越大 → 路徑演算法更積極繞道走陰涼處
  </div>
</div>""", unsafe_allow_html=True)

    with sw2:
        # 完整氣象數值彙整表
        st.markdown('<p class="section-title">📋 完整觀測彙整</p>', unsafe_allow_html=True)
        summary_data = {
            "項目": ["氣溫","相對濕度","風速","降雨量","體感溫度","熱指數","WBGT","UV 指數","UV 等級","AQI","AQI 狀態","PM2.5 最近站","PM2.5 Kriging","PM2.5 等級","熱危害等級","陰影加權倍率"],
            "數值": [
                w.temperature,
                w.humidity,
                w.wind_speed,
                w.precipitation,
                w.apparent_temp,
                w.heat_index,
                w.wbgt,
                w.uv_index,
                w.uv_level,
                w.aqi,
                w.aqi_status or "Unavailable",
                w.pm25,
                w.pm25_kriging,
                w.pm25_level,
                w.heat_risk,
                w.shadow_weight_multiplier,
            ],
        }
        st.dataframe(
            pd.DataFrame(summary_data)
            .style.format({"數值": lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else str(x) if x is not None else "N/A"})
            .set_properties(**{"background-color":"#13161f","color":"#ccd6f6",
                             "border-color":"#1e2130"}),
            use_container_width=True, height=520, hide_index=True,
        )
