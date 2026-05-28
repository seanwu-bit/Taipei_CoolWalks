import os
import sys
import logging
import json
import networkx as nx
import requests
from dotenv import load_dotenv

# 設定 logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 將 scripts 目錄加入 path 以前後相容導入 graphml_utils
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from graphml_utils import load_graphml_custom

def calculate_path_stats(G, path_nodes, weight_attr):
    """
    計算最佳路徑的物理長度與總權重成本（考慮 MultiDiGraph 中兩節點間有多條邊的情況）。
    """
    total_length = 0.0
    total_cost = 0.0
    
    for u, v in zip(path_nodes[:-1], path_nodes[1:]):
        edges_data = G[u][v]
        # 尋找指定權重（如 cost）最小的邊
        best_edge = min(edges_data.values(), key=lambda x: x.get(weight_attr, float('inf')))
        total_cost += best_edge.get(weight_attr, 0.0)
        total_length += best_edge.get('length', 0.0)
        
    return total_length, total_cost

def calculate_path_exposure_stats(G, path_nodes, weight_attr):
    """
    計算最佳路徑的環境暴露指標（長度加權平均值）。
    """
    total_len = 0.0
    weighted_wbgt = 0.0
    weighted_shading = 0.0
    weighted_shadow = 0.0
    weighted_pm25 = 0.0
    weighted_uv = 0.0
    weighted_safety = 0.0
    
    for u, v in zip(path_nodes[:-1], path_nodes[1:]):
        edges_data = G[u][v]
        # 尋找指定權重最小的邊
        best_edge = min(edges_data.values(), key=lambda x: x.get(weight_attr, float('inf')))
        
        edge_len = float(best_edge.get('length', 1.0))
        total_len += edge_len
        
        weighted_wbgt += float(best_edge.get('dynamic_wbgt_c', 20.0)) * edge_len
        weighted_shading += float(best_edge.get('shading_index', 0.0)) * edge_len
        weighted_shadow += float(best_edge.get('dynamic_shadow_ratio', 0.0)) * edge_len
        weighted_pm25 += float(best_edge.get('dynamic_pm25_kriging', 0.0)) * edge_len
        weighted_uv += float(best_edge.get('dynamic_uv_index', 0.0)) * edge_len
        weighted_safety += float(best_edge.get('safety_score', 1.0)) * edge_len
        
    if total_len > 0:
        return {
            "avg_wbgt": weighted_wbgt / total_len,
            "avg_shading": weighted_shading / total_len,
            "avg_shadow": weighted_shadow / total_len,
            "avg_pm25": weighted_pm25 / total_len,
            "avg_uv": weighted_uv / total_len,
            "avg_safety": weighted_safety / total_len
        }
    else:
        return {
            "avg_wbgt": 20.0,
            "avg_shading": 0.0,
            "avg_shadow": 0.0,
            "avg_pm25": 0.0,
            "avg_uv": 0.0,
            "avg_safety": 1.0
        }

def get_fallback_health_advice(case_name, stats):
    """
    本地備用建議生成器（在 API 無效或無網路時防崩潰使用）。
    """
    avg_wbgt = stats["avg_wbgt"]
    avg_pm25 = stats["avg_pm25"]
    avg_safety = stats["avg_safety"]
    
    eval_text = "【路段健康評估】本路線整體環境指標尚可。 "
    if avg_wbgt > 28:
        eval_text = "【路段健康評估】本路線平均溫度較高，熱壓力偏大，缺乏充足遮陰。 "
    elif avg_pm25 > 35:
        eval_text = "【路段健康評估】本路線細懸浮微粒 (PM2.5) 暴露濃度較高，空氣品質不佳。 "
    elif avg_safety < 0.6:
        eval_text = "【路段健康評估】本路線平均安全防護得分偏低，部分路段可能缺乏實體人行道。 "
        
    adv_text = "【防護出行建議】建議出行時攜帶防曬用品並隨時補充水分。"
    tips = []
    if avg_wbgt > 28:
        tips.append("請多利用建築物陰影或騎樓避暑步行，避免正午暴晒")
    if avg_pm25 > 35:
        tips.append("空污敏感族群出行建議配戴口罩")
    if avg_safety < 0.6:
        tips.append("行經無人行道窄巷時請特別注意周邊車流")
        
    if tips:
        adv_text = "【防護出行建議】" + "；".join(tips) + "。隨時補充水分，注意步行安全。"
        
    return eval_text + "\n" + adv_text

def get_gemini_health_advice(case_name, total_length, stats):
    """
    呼叫 Gemini API 獲取個人化醫療保健與戶外出行建議。
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dotenv_path = os.path.abspath(os.path.join(script_dir, "..", ".env"))
    load_dotenv(dotenv_path)
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logging.warning("未偵測到 GEMINI_API_KEY，將啟用本地規則引擎備用建議。")
        return get_fallback_health_advice(case_name, stats)
        
    avg_wbgt = stats["avg_wbgt"]
    avg_shading = stats["avg_shading"]
    avg_shadow = stats["avg_shadow"]
    avg_pm25 = stats["avg_pm25"]
    avg_uv = stats["avg_uv"]
    avg_safety = stats["avg_safety"]
    
    prompt = f"""
你是一位專業的都市環境健康與公共衛生專家。以下是行人在某條步道路線上的環境暴露數據：
- 路線名稱: {case_name}
- 路線長度: {total_length:.1f} 公尺
- 均衡通勤情境下之暴露值：
  - 平均乾濕球溫度 (WBGT): {avg_wbgt:.1f}°C
  - 平均綠意遮陰率: {avg_shading:.2%}
  - 平均建物陰影遮陰率: {avg_shadow:.2%}
  - 平均細懸浮微粒 (PM2.5) 濃度: {avg_pm25:.1f} µg/m³
  - 平均紫外線指數: {avg_uv:.1f}
  - 平均道路安全得分: {avg_safety:.2f} (範圍 0.0~1.0，越低代表越缺乏安全人行空間)

請根據這些實際數據，為一般通勤者、孩童及銀髮族，提供一份繁體中文的「醫療保健與戶外出行建議」。
格式要求：
1. 字數限制在 200 字以內。
2. 分為「路段健康評估」與「防護出行建議」兩個小區塊。
3. 若高溫或空污較高、或是安全得分較低，請針對性給予具體警示（如：防曬、配戴口罩、注意車流等）。
4. 輸出文字必須是繁體中文。請直接輸出建議內容，不要包含額外的說明字句。
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    try:
        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
        if response.status_code == 200:
            res_json = response.json()
            advice = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
            # 移除一些 markdown 標示或額外引號 (如果有)
            advice = advice.replace("```json", "").replace("```", "").strip()
            logging.info(f"成功取得 Gemini API 生成之醫療保健建議。")
            return advice
        else:
            logging.error(f"Gemini API 請求失敗，狀態碼: {response.status_code}，錯誤內容: {response.text}")
            return get_fallback_health_advice(case_name, stats)
    except Exception as e:
        logging.error(f"呼叫 Gemini API 時發生異常: {e}")
        return get_fallback_health_advice(case_name, stats)

def run_path_router(input_path, output_path):
    logging.info("===== M3 Path Router 開始執行 =====")
    logging.info(f"輸入圖資路徑：{input_path}")
    logging.info(f"輸出 JSON 路徑：{output_path}")
    
    # 1. 載入計算阻力後的圖資
    try:
        G = load_graphml_custom(input_path)
        logging.info(f"成功載入圖資。節點數：{G.number_of_nodes()}，路段數：{G.number_of_edges()}")
    except Exception as e:
        logging.error(f"載入圖資失敗：{e}")
        sys.exit(1)
        
    # 2. 載入現有 JSON 作為快取
    existing_data = {}
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
            logging.info("成功載入現有的路徑 JSON 快取。")
        except Exception as e:
            logging.warning(f"載入現有路徑快取失敗：{e}")

    # 定義路徑規劃測試案例 (Node ID 使用字串格式)
    cases = {
        "case1": {
            "name": "跨校區通勤情境 (台大至師大)",
            "start": "6240955569",
            "end": "4266400151"
        },
        "case2": {
            "name": "生活消費與跨主幹道情境 (土研大樓至永康街商圈)",
            "start": "12263412046",
            "end": "5051817857"
        }
    }
    
    # 支持的特定情境（用於產生多情境比較路徑）
    scenarios = ['balanced', 'heat_averse', 'safety_first']
    
    output_data = {}
    
    for case_id, info in cases.items():
        logging.info(f"開始分析 {info['name']}...")
        start_node = info['start']
        end_node = info['end']
        
        # 檢查節點是否存在於路網中
        if start_node not in G:
            logging.error(f"  起點節點 {start_node} 不在路網中！")
            continue
        if end_node not in G:
            logging.error(f"  終點節點 {end_node} 不在路網中！")
            continue
            
        # A. 計算主線路徑（以當前預設之 'cost' 為權重）
        try:
            path_nodes = nx.shortest_path(G, source=start_node, target=end_node, weight='cost')
            tot_len, tot_cost = calculate_path_stats(G, path_nodes, 'cost')
            logging.info(f"  [預設路徑] 求解成功！節點數：{len(path_nodes)}，總長度：{tot_len:.2f} m，總阻力成本：{tot_cost:.2f}")
        except nx.NetworkNoPath:
            logging.error(f"  [預設路徑] 起點 {start_node} 到終點 {end_node} 之間無可行路徑！")
            continue
            
        # B. 計算多情境下的最佳路徑以供視覺化與比較
        scenario_paths = {}
        for sc in scenarios:
            weight_attr = f'cost_{sc}'
            try:
                sc_path_nodes = nx.shortest_path(G, source=start_node, target=end_node, weight=weight_attr)
                sc_len, sc_cost = calculate_path_stats(G, sc_path_nodes, weight_attr)
                scenario_paths[sc] = {
                    "path": sc_path_nodes,
                    "total_length": sc_len,
                    "total_cost": sc_cost
                }
                logging.info(f"  [{sc} 情境] 求解成功！節點數：{len(sc_path_nodes)}，長度：{sc_len:.2f} m，成本：{sc_cost:.2f}")
            except Exception as e:
                logging.warning(f"  [{sc} 情境] 求解失敗：{e}")
                
        # C. 擷取路面環境指標與呼叫 API (整合快取機制)
        stats = calculate_path_exposure_stats(G, path_nodes, 'cost')
        health_advice = None
        if case_id in existing_data:
            old_case = existing_data[case_id]
            if old_case.get("path") == path_nodes and "health_advice" in old_case:
                health_advice = old_case["health_advice"]
                logging.info(f"  [快取命中] 路線未變更，沿用舊有的 Gemini 醫療保健建議。")
                
        if health_advice is None:
            logging.info(f"  路線已變更或快取不存在，呼叫 Gemini API 取得新建議...")
            health_advice = get_gemini_health_advice(info['name'], tot_len, stats)
            
        output_data[case_id] = {
            "case_name": info['name'],
            "start_node": start_node,
            "end_node": end_node,
            "path": path_nodes,
            "total_length": tot_len,
            "total_cost": tot_cost,
            "stats": stats,
            "health_advice": health_advice,
            "scenarios": scenario_paths
        }
        
    # 寫入 JSON 檔案
    try:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)
        logging.info(f"成功將最佳路徑資料寫入 JSON：{output_path}")
    except Exception as e:
        logging.error(f"寫入 JSON 失敗：{e}")
        sys.exit(1)
        
    logging.info("===== M3 Path Router 執行完畢 =====")

if __name__ == "__main__":
    # 解析路徑
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.abspath(os.path.join(script_dir, "..", "outputs", "M2_costed_network.graphml"))
    output_file = os.path.abspath(os.path.join(script_dir, "..", "outputs", "M3_optimal_paths.json"))
    
    run_path_router(input_file, output_file)
