import os
import sys
import logging
import json
import folium
import branca.colormap as cm

# 設定 logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 將 scripts 目錄加入 path 以前後相容導入 graphml_utils
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from graphml_utils import load_graphml_custom

def clip(val, min_val, max_val):
    return min(max(val, min_val), max_val)

def get_edge_coords(G, u, v, data):
    """
    獲取路段的 GPS 經緯度點序列，若無 geometry 屬性則使用兩節點坐標直線相連。
    """
    if 'geometry' in data and data['geometry']:
        try:
            geom_str = data['geometry'].replace('LINESTRING (', '').replace('LINESTRING(', '').replace(')', '')
            coords = []
            for pt in geom_str.split(','):
                parts = pt.strip().split()
                if len(parts) >= 2:
                    x, y = float(parts[0]), float(parts[1])
                    coords.append([y, x])  # Folium 使用 [y, x]（緯度, 經度）
            return coords
        except Exception:
            pass
            
    # 備用方案：使用節點起終點直線連接
    y1, x1 = G.nodes[u]['y'], G.nodes[u]['x']
    y2, x2 = G.nodes[v]['y'], G.nodes[v]['x']
    return [[y1, x1], [y2, x2]]

def generate_popup_html(case_name, case_data):
    """
    為起終點 Marker 產生精美的 HTML Popup，展示均衡通勤模式下的路徑長度、阻力成本，並整合健康建議。
    """
    length = case_data['total_length']
    cost = case_data['total_cost']
    advice = case_data.get('health_advice', '暫無出行建議。')
    advice_html = advice.replace('\n', '<br>')
    
    html = f"""
    <div style="font-family: 'Microsoft JhengHei', sans-serif; width: 260px; font-size: 12px; line-height: 1.5; color: #333; max-height: 300px; overflow-y: auto;">
        <h4 style="margin: 0 0 8px 0; color: #333; border-bottom: 2px solid #1f77b4; padding-bottom: 4px; font-size: 14px; font-weight: bold;">{case_name}</h4>
        <p style="margin: 4px 0;"><b>情境模式</b>：均衡通勤模式 (Balanced)</p>
        <p style="margin: 4px 0;"><b>路徑長度</b>：{length:.1f} 公尺</p>
        <p style="margin: 4px 0;"><b>通行阻力成本</b>：{cost:.2f}</p>
        <hr style="margin: 8px 0; border: 0; border-top: 1px solid #ddd;">
        <div style="background-color: #fff9e6; padding: 8px 10px; border-radius: 4px; border-left: 4px solid #f0ad4e; margin-top: 4px; border-right: 1px solid #fbeed5; border-top: 1px solid #fbeed5; border-bottom: 1px solid #fbeed5;">
            <span style="font-weight: bold; color: #b9881a; display: block; margin-bottom: 4px;">💡 出行保健提示：</span>
            <div style="font-size: 11px; line-height: 1.5; color: #66512c; text-align: justify;">
                {advice_html}
            </div>
        </div>
    </div>
    """
    return html

def generate_health_advice_popup_html(case_name, case_data):
    """
    為最佳路徑折線點擊產生專屬的 HTML Popup，展示環境暴露平均值與 Gemini 醫療保健與出行建議。
    """
    length = case_data['total_length']
    cost = case_data['total_cost']
    stats = case_data.get('stats', {})
    advice = case_data.get('health_advice', '暫無健康出行建議。')
    
    avg_wbgt = stats.get('avg_wbgt', 20.0)
    avg_pm25 = stats.get('avg_pm25', 0.0)
    avg_uv = stats.get('avg_uv', 0.0)
    avg_shading = stats.get('avg_shading', 0.0)
    avg_shadow = stats.get('avg_shadow', 0.0)
    avg_safety = stats.get('avg_safety', 1.0)
    
    advice_html = advice.replace('\n', '<br>')
    
    html = f"""
    <div style="font-family: 'Microsoft JhengHei', sans-serif; width: 280px; line-height: 1.5; font-size: 12px; color: #333; max-height: 380px; overflow-y: auto;">
        <h4 style="margin: 0 0 8px 0; color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 4px; font-size: 14px; font-weight: bold;">
            💡 均衡通勤路徑分析與保健建議
        </h4>
        <div style="background-color: #f8f9fa; padding: 6px 10px; border-radius: 4px; margin-bottom: 8px; font-size: 11px; border: 1px solid #e9ecef;">
            <p style="margin: 3px 0;"><b>總長度</b>：{length:.1f} 公尺</p>
            <p style="margin: 3px 0;"><b>通行阻力成本</b>：{cost:.2f}</p>
            <p style="margin: 3px 0;"><b>平均溫度 (WBGT)</b>：{avg_wbgt:.1f}°C</p>
            <p style="margin: 3px 0;"><b>平均綠意遮陰率</b>：{avg_shading:.1%}</p>
            <p style="margin: 3px 0;"><b>平均建物遮陰率</b>：{avg_shadow:.1%}</p>
            <p style="margin: 3px 0;"><b>平均 PM2.5 濃度</b>：{avg_pm25:.1f} µg/m³</p>
            <p style="margin: 3px 0;"><b>平均紫外線指數</b>：{avg_uv:.1f}</p>
            <p style="margin: 3px 0;"><b>道路安全得分</b>：{avg_safety:.2f}</p>
        </div>
        <div style="background-color: #eaf2f8; padding: 8px 12px; border-radius: 4px; border-left: 4px solid #2980b9; margin-bottom: 4px; border-right: 1px solid #d4e6f1; border-top: 1px solid #d4e6f1; border-bottom: 1px solid #d4e6f1;">
            <span style="font-weight: bold; color: #2980b9; display: block; margin-bottom: 4px;">Gemini 專業出行建議：</span>
            <div style="font-size: 11px; line-height: 1.5; text-align: justify; color: #2c3e50;">
                {advice_html}
            </div>
        </div>
    </div>
    """
    return html

def run_map_visualizer(network_path, paths_path, html_output_path):
    logging.info("===== M4 Map Visualizer 開始執行 =====")
    logging.info(f"輸入圖資路徑：{network_path}")
    logging.info(f"輸入路徑 JSON 路徑：{paths_path}")
    logging.info(f"輸出 HTML 地圖路徑：{html_output_path}")
    
    # 1. 載入圖資與最佳路徑 JSON
    try:
        G = load_graphml_custom(network_path)
        logging.info(f"成功載入圖資。節點數：{G.number_of_nodes()}，路段數：{G.number_of_edges()}")
    except Exception as e:
        logging.error(f"載入圖資失敗：{e}")
        sys.exit(1)
        
    try:
        with open(paths_path, 'r', encoding='utf-8') as f:
            paths_data = json.load(f)
        logging.info("成功載入最佳路徑 JSON 資料。")
    except Exception as e:
        logging.error(f"載入 JSON 失敗：{e}")
        sys.exit(1)
        
    # 2. 計算地圖中心點 (大安區)
    y_coords = [data['y'] for node, data in G.nodes(data=True) if 'y' in data]
    x_coords = [data['x'] for node, data in G.nodes(data=True) if 'x' in data]
    center_y = sum(y_coords) / len(y_coords) if y_coords else 25.025
    center_x = sum(x_coords) / len(x_coords) if x_coords else 121.535
    
    # 3. 初始化 Folium 地圖
    m = folium.Map(
        location=[center_y, center_x],
        zoom_start=14,
        tiles="CartoDB positron", # 使用簡潔優雅的淡色底圖，以便突顯路網色彩
        control_scale=True
    )
    
    # 4. Phase 1: 建立絕對分級機制與鎖定色彩圖例 (Color Map)
    vmin, vmax = 1.0, 3.0
    colormap = cm.LinearColormap(
        colors=['green', '#ffd700', '#ff8c00', 'red'], # 綠色 -> 黃色 -> 橘色 -> 紅色
        vmin=vmin,
        vmax=vmax
    )
    colormap.caption = "道路通行單位距離阻力成本 (Unit Cost)"
    colormap.add_to(m)
    
    # 5. 採用 Multi-Polyline 優化技術繪製全區底圖，防止瀏覽器當機
    logging.info("開始整合與繪製全區步行阻力底圖...")
    num_bins = 20
    color_bins = {i: {
        'val': vmin + (vmax - vmin) * (i / (num_bins - 1)),
        'color': colormap(vmin + (vmax - vmin) * (i / (num_bins - 1))),
        'lines': []
    } for i in range(num_bins)}
    
    for u, v, k, data in G.edges(keys=True, data=True):
        unit_cost = float(data.get('unit_cost', 1.0))
        clamped_unit_cost = clip(unit_cost, vmin, vmax)
        
        # 尋找最近的分桶索引
        bin_idx = int((clamped_unit_cost - vmin) / (vmax - vmin) * (num_bins - 1))
        bin_idx = clip(bin_idx, 0, num_bins - 1)
        
        coords = get_edge_coords(G, u, v, data)
        color_bins[bin_idx]['lines'].append(coords)
        
    # 將分桶後的折線分別加入底圖圖層
    base_road_layer = folium.FeatureGroup(name="大安區道路步行阻力 (Unit Cost)", overlay=True, control=True)
    for idx, bin_data in color_bins.items():
        if bin_data['lines']:
            folium.PolyLine(
                locations=bin_data['lines'],
                color=bin_data['color'],
                weight=2.0,
                opacity=0.6,
                smooth_factor=1.0
            ).add_to(base_road_layer)
    base_road_layer.add_to(m)
    
    # 6. Phase 2: 最佳路徑疊加與圖層控制 (FeatureGroup)
    logging.info("開始繪製各案例最佳路徑與 Marker...")
    
    # 定義 Case 地圖樣式
    case_styles = {
        "case1": {
            "name": "Case 1: 均衡通勤模式 (台大至師大)",
            "color_main": "#1f77b4",       # 深藍色
            "start_desc": "起點：國立臺灣大學",
            "end_desc": "終點：國立臺灣師範大學"
        },
        "case2": {
            "name": "Case 2: 均衡通勤模式 (土研至永康街)",
            "color_main": "#9467bd",       # 深紫色
            "start_desc": "起點：台大土研大樓",
            "end_desc": "終點：永康街商圈"
        }
    }
    
    for case_id, case_style in case_styles.items():
        if case_id not in paths_data:
            logging.warning(f"JSON 中找不到 {case_id} 的路徑資料！")
            continue
            
        case_data = paths_data[case_id]
        
        # 建立專屬 FeatureGroup
        case_group = folium.FeatureGroup(name=case_style['name'], overlay=True, control=True)
        
        # A. 繪製均衡通勤模式路徑 (加粗 weight=6)
        path_nodes = case_data['path']
        path_coords = []
        for node_id in path_nodes:
            if node_id in G:
                path_coords.append([G.nodes[node_id]['y'], G.nodes[node_id]['x']])
                
        if len(path_coords) >= 2:
            # 建立健康出行建議與分析 Popups
            health_popup_content = generate_health_advice_popup_html(case_style['name'], case_data)
            
            folium.PolyLine(
                locations=path_coords,
                color=case_style['color_main'],
                weight=6,
                opacity=0.9,
                tooltip=f"{case_style['name']} (點擊查看醫療保健建議)",
                popup=folium.Popup(health_popup_content, max_width=320)
            ).add_to(case_group)
                
        # C. 加上起點與終點 Marker 標記
        start_node_id = case_data['start_node']
        end_node_id = case_data['end_node']
        
        marker_popup_html = generate_popup_html(case_style['name'], case_data)
        
        if start_node_id in G:
            start_coord = [G.nodes[start_node_id]['y'], G.nodes[start_node_id]['x']]
            # 起點 Marker
            folium.Marker(
                location=start_coord,
                popup=folium.Popup(marker_popup_html, max_width=320),
                tooltip=f"<b>起點</b>: {case_style['start_desc']}",
                icon=folium.Icon(color='green', icon='play', prefix='fa')
            ).add_to(case_group)
            
        if end_node_id in G:
            end_coord = [G.nodes[end_node_id]['y'], G.nodes[end_node_id]['x']]
            # 終點 Marker
            folium.Marker(
                location=end_coord,
                popup=folium.Popup(marker_popup_html, max_width=320),
                tooltip=f"<b>終點</b>: {case_style['end_desc']}",
                icon=folium.Icon(color='red', icon='stop', prefix='fa')
            ).add_to(case_group)
            
        # 將該案例圖層加入地圖
        case_group.add_to(m)
        
    # 7. 加入圖層切換控制 LayerControl
    folium.LayerControl(position='topright').add_to(m)
    
    # 8. 儲存 HTML 地圖
    try:
        os.makedirs(os.path.dirname(os.path.abspath(html_output_path)), exist_ok=True)
        m.save(html_output_path)
        logging.info(f"成功儲存互動式網頁地圖：{html_output_path}")
    except Exception as e:
        logging.error(f"儲存 HTML 失敗：{e}")
        sys.exit(1)
        
    logging.info("===== M4 Map Visualizer 執行完畢 =====")

if __name__ == "__main__":
    # 解析路徑
    script_dir = os.path.dirname(os.path.abspath(__file__))
    network_file = os.path.abspath(os.path.join(script_dir, "..", "outputs", "M2_costed_network.graphml"))
    paths_file = os.path.abspath(os.path.join(script_dir, "..", "outputs", "M3_optimal_paths.json"))
    output_html = os.path.abspath(os.path.join(script_dir, "..", "outputs", "M4_routing_result.html"))
    
    run_map_visualizer(network_file, paths_file, output_html)
