import os
import sys
import logging
import argparse

# 設定 logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 將 scripts 目錄加入 path 以前後相容導入 graphml_utils
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from graphml_utils import load_graphml_custom, write_graphml_custom

def clip(val, min_val, max_val):
    return min(max(val, min_val), max_val)

def run_cost_calculator(input_path, output_path, scenario):
    logging.info("===== M2 Cost Calculator 開始執行 =====")
    logging.info(f"輸入檔案路徑：{input_path}")
    logging.info(f"輸出檔案路徑：{output_path}")
    logging.info(f"指定情境模式：{scenario}")
    
    # 1. 載入已驗證的圖資
    try:
        G = load_graphml_custom(input_path)
        logging.info(f"成功載入圖資。節點數：{G.number_of_nodes()}，路段數：{G.number_of_edges()}")
    except Exception as e:
        logging.error(f"載入圖資失敗：{e}")
        sys.exit(1)
        
    # 情境權重定義
    scenarios_weights = {
        'balanced': {'W_env': 1.0, 'W_safe': 1.0, 'W_air': 0.5},
        'heat_averse': {'W_env': 2.0, 'W_safe': 0.5, 'W_air': 0.2},
        'safety_first': {'W_env': 0.5, 'W_safe': 2.0, 'W_air': 0.5}
    }
    
    if scenario not in scenarios_weights:
        logging.error(f"未知情境模式：{scenario}。僅支援：{list(scenarios_weights.keys())}")
        sys.exit(1)
        
    # 常數權重
    alpha = 0.8
    beta = 0.2
    
    # 2. 計算阻力成本
    logging.info("開始計算路段阻力與通行成本...")
    
    for u, v, k, data in G.edges(keys=True, data=True):
        # 提取指標（此時必定存在且已填補，但為防萬一仍設置預設）
        length = float(data.get('length', 1.0))
        shading_index = float(data.get('shading_index', 0.0))
        safety_score = float(data.get('safety_score', 1.0))
        dynamic_shadow_ratio = float(data.get('dynamic_shadow_ratio', 0.0))
        dynamic_wbgt_c = float(data.get('dynamic_wbgt_c', 20.0))
        dynamic_uv_index = float(data.get('dynamic_uv_index', 0.0))
        dynamic_pm25_kriging = float(data.get('dynamic_pm25_kriging', 0.0))
        
        # 指標預處理與截斷 (Clipping)
        S_green = clip(shading_index, 0.0, 1.0)
        S_bldg = clip(dynamic_shadow_ratio, 0.0, 1.0)
        Safety = clip(safety_score, 0.0, 1.0)
        
        # 熱壓力與空污正規化 (Normalization)
        T_norm = clip((dynamic_wbgt_c - 20.0) / (33.0 - 20.0), 0.0, 1.0)
        UV_norm = clip(dynamic_uv_index / 11.0, 0.0, 1.0)
        PM_norm = clip(dynamic_pm25_kriging / 50.0, 0.0, 1.0)
        
        # 綜合遮陰率與環境熱壓力懲罰
        S_total = S_green + S_bldg - (S_green * S_bldg)
        P_env = (alpha * T_norm + beta * UV_norm) * (1.0 - S_total)
        
        # 安全與空污懲罰
        P_safe = 1.0 - Safety
        P_air = PM_norm
        
        # 計算三種情境模式的通行成本與單位距離成本
        for sc_name, w in scenarios_weights.items():
            w_env = w['W_env']
            w_safe = w['W_safe']
            w_air = w['W_air']
            
            # 單位距離成本 (Unit Cost)
            unit_cost_val = 1.0 + w_env * P_env + w_safe * P_safe + w_air * P_air
            # 總成本 (Cost)
            cost_val = length * unit_cost_val
            
            # 寫入對應情境的特定欄位
            G[u][v][k][f'cost_{sc_name}'] = cost_val
            G[u][v][k][f'unit_cost_{sc_name}'] = unit_cost_val
            
        # 將指定的情境值賦予標準的 cost 與 unit_cost 欄位
        G[u][v][k]['cost'] = G[u][v][k][f'cost_{scenario}']
        G[u][v][k]['unit_cost'] = G[u][v][k][f'unit_cost_{scenario}']
        
    # 3. 輸出計算完成之圖資
    try:
        write_graphml_custom(G, output_path)
        logging.info(f"成功將計算阻力後的圖資寫入：{output_path}")
    except Exception as e:
        logging.error(f"寫入圖資失敗：{e}")
        sys.exit(1)
        
    logging.info("===== M2 Cost Calculator 執行完畢 =====")

if __name__ == "__main__":
    # 解析命令列參數
    parser = argparse.ArgumentParser(description="大安區路段阻力成本計算模組")
    parser.add_argument(
        '-s', '--scenario', 
        choices=['balanced', 'heat_averse', 'safety_first'], 
        default='balanced',
        help='選擇情境模式（均衡通勤、極端避暑、弱勢行人，預設為 balanced）'
    )
    args = parser.parse_args()
    
    # 解析路徑
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.abspath(os.path.join(script_dir, "..", "outputs", "M1_validated_network.graphml"))
    output_file = os.path.abspath(os.path.join(script_dir, "..", "outputs", "M2_costed_network.graphml"))
    
    run_cost_calculator(input_file, output_file, args.scenario)
