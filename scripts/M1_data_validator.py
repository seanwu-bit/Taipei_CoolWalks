import os
import sys
import logging

# 設定 logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 將 scripts 目錄加入 path 以前後相容導入 graphml_utils
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from graphml_utils import load_graphml_custom, write_graphml_custom

def run_data_validator(input_path, output_path):
    logging.info("===== M1 Data Validator 開始執行 =====")
    logging.info(f"輸入檔案路徑：{input_path}")
    logging.info(f"輸出檔案路徑：{output_path}")
    
    # 1. 載入圖資
    try:
        G = load_graphml_custom(input_path)
        logging.info(f"成功載入圖資。節點數：{G.number_of_nodes()}，路段數：{G.number_of_edges()}")
    except Exception as e:
        logging.error(f"載入圖資失敗：{e}")
        sys.exit(1)
        
    # 7 個關鍵指標欄位
    critical_attributes = [
        'length',
        'shading_index',
        'safety_score',
        'dynamic_shadow_ratio',
        'dynamic_wbgt_c',
        'dynamic_uv_index',
        'dynamic_pm25_kriging'
    ]
    
    # 防呆預設基準值（當欄位完全無有效值時使用）
    fallback_defaults = {
        'length': 1.0,
        'shading_index': 0.1,
        'safety_score': 0.5,
        'dynamic_shadow_ratio': 0.0,
        'dynamic_wbgt_c': 25.0,
        'dynamic_uv_index': 5.0,
        'dynamic_pm25_kriging': 15.0
    }
    
    # 2. 計算全區有效資料的平均值
    logging.info("開始計算各指標之全區平均值...")
    valid_values = {attr: [] for attr in critical_attributes}
    
    for u, v, k, data in G.edges(keys=True, data=True):
        for attr in critical_attributes:
            val = data.get(attr)
            if val is not None:
                try:
                    # 嘗試轉換成 float 來驗證
                    float_val = float(val)
                    valid_values[attr].append(float_val)
                except ValueError:
                    pass
                    
    # 計算各屬性的平均值，若無有效值則套用備用預設值
    imputation_values = {}
    for attr in critical_attributes:
        vals = valid_values[attr]
        if vals:
            imputation_values[attr] = sum(vals) / len(vals)
            logging.info(f"  {attr} 平均值：{imputation_values[attr]:.6f}")
        else:
            imputation_values[attr] = fallback_defaults[attr]
            logging.warning(f"  {attr} 無任何有效數值，將採用預設基準值：{imputation_values[attr]}")
            
    # 3. 遍歷 edges 進行檢查與缺失值填補 (Imputation)
    imputed_counts = {attr: 0 for attr in critical_attributes}
    
    for u, v, k, data in G.edges(keys=True, data=True):
        for attr in critical_attributes:
            val = data.get(attr)
            is_missing = False
            
            if val is None:
                is_missing = True
            else:
                try:
                    # 檢查是否為有效數值
                    float_val = float(val)
                    # 排除 NaN
                    import math
                    if math.isnan(float_val):
                        is_missing = True
                except ValueError:
                    is_missing = True
                    
            if is_missing:
                # 填補缺失值
                fill_val = imputation_values[attr]
                G[u][v][k][attr] = fill_val
                imputed_counts[attr] += 1
                
    # 4. 輸出填補統計
    logging.info("缺失值填補統計：")
    for attr in critical_attributes:
        logging.info(f"  {attr} 填補次數：{imputed_counts[attr]}")
        
    # 5. 導出圖資
    try:
        write_graphml_custom(G, output_path)
        logging.info(f"成功將驗證後的圖資寫入：{output_path}")
    except Exception as e:
        logging.error(f"寫入圖資失敗：{e}")
        sys.exit(1)
        
    logging.info("===== M1 Data Validator 執行完畢 =====")

if __name__ == "__main__":
    # 解析路徑（相對於腳本位置）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.abspath(os.path.join(script_dir, "..", "data", "Daan_Shaded_Network(還原)_dynamic_v1.graphml"))
    output_file = os.path.abspath(os.path.join(script_dir, "..", "outputs", "M1_validated_network.graphml"))
    
    run_data_validator(input_file, output_file)
