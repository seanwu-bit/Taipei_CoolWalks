import os
import sys
import subprocess
import logging
import json

# 設定 logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run_script(script_name, args=[]):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(script_dir, script_name)
    
    cmd = [sys.executable, "-u", script_path] + args
    logging.info(f"執行指令: {' '.join(cmd)}")
    
    # 執行並實時轉發 stdout/stderr
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
    
    if result.returncode != 0:
        logging.error(f"腳本 {script_name} 執行失敗！錯誤碼: {result.returncode}")
        print("--- 標準輸出 ---")
        print(result.stdout)
        print("--- 標準錯誤 ---")
        print(result.stderr)
        sys.exit(1)
        
    logging.info(f"腳本 {script_name} 執行成功。")
    return result.stdout

def main():
    logging.info("=========================================")
    logging.info("   開始執行大安區行人適性路網 Pipeline")
    logging.info("=========================================")
    
    # 1. 執行 M1: 資料驗證與補值
    run_script("M1_data_validator.py")
    
    # 2. 執行 M2: 成本計算 (均衡通勤模式)
    run_script("M2_cost_calculator.py", ["--scenario", "balanced"])
    
    # 3. 執行 M3: 最佳路徑求解
    run_script("M3_path_router.py")
    
    # 4. 執行 M4: 互動式地圖視覺化
    run_script("M4_map_visualizer.py")
    
    # 5. 讀取 M3 結果 JSON 以在主控台輸出報告
    script_dir = os.path.dirname(os.path.abspath(__file__))
    paths_json_path = os.path.abspath(os.path.join(script_dir, "..", "outputs", "M3_optimal_paths.json"))
    html_map_path = os.path.abspath(os.path.join(script_dir, "..", "outputs", "M4_routing_result.html"))
    
    print("\n" + "="*50)
    print("           路徑規劃與成本分析報告")
    print("="*50)
    
    if os.path.exists(paths_json_path):
        with open(paths_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        for case_id, info in data.items():
            print(f"\n[{info['case_name']}]")
            print(f"  - 起點 Node ID: {info['start_node']}")
            print(f"  - 終點 Node ID: {info['end_node']}")
            print(f"  - 預設最佳路徑節點數: {len(info['path'])}")
            
            scs = info.get('scenarios', {})
            for sc_name, sc_data in scs.items():
                sc_label = {
                    'balanced': '均衡通勤模式',
                    'heat_averse': '極端避暑模式',
                    'safety_first': '弱勢行人模式'
                }.get(sc_name, sc_name)
                print(f"    * {sc_label}: 長度 = {sc_data['total_length']:.1f} m | 總通行成本 = {sc_data['total_cost']:.2f}")
    else:
        print("找不到路徑分析結果檔案 M3_optimal_paths.json")
        
    print("\n" + "="*50)
    print(f"互動式地圖已成功產出，存檔路徑如下：\n{html_map_path}")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
