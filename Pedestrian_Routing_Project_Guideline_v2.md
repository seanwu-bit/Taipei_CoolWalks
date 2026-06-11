# 大安區行人適性路徑規劃成本計算與導航模組專案指引 (v2.0)

## 1. 專案概述與執行環境
本專案旨在開發一個整合「靜態建成環境」與「動態微氣候變數」的行人適性路徑規劃系統。透過量化行人在都市環境中所面臨的熱壓力、空氣污染與交通安全阻力，設計一個學術嚴謹的成本函數 (Cost Function)，並利用 Dijkstra 演算法尋找最舒適且安全的步行路線。

### 執行環境規範
- **執行環境名稱**：`geospatial`
- **目錄結構**：
  - 所有實體執行的 Python 腳本皆必須存放於 `scripts/` 資料夾中。
  - 所有模組產出的實體檔案（包含 GraphML、JSON、HTML 地圖）皆必須存放於 `outputs/` 資料夾中。
  - 腳本中讀寫檔案必須使用相對路徑（例如：`../outputs/filename`）。

---

## 2. 資料結構說明 (GraphML Edge Attributes)
輸入的大安區路網圖（`.graphml`）中，每個 Edge（路段）必須包含以下 **7 個關鍵參數**。若欄位缺失，將無法進行後續運算：

### 靜態指標 (Static Indicators)
1. `length`：路段實體物理長度 (公尺)。
2. `shading_index`：綠意遮陰率 (原始數值區間約為 0.0 ~ 2.0，本案研究範圍主要落在 0.0135 ~ 0.7082)，代表樹冠提供的綠蔭程度。
3. `safety_score`：行人安全係數 (0.0 ~ 1.0)，數值越高代表越安全（如：設有實體人行道、車流量低）。

### 動態指標 (Dynamic Indicators)
4. `dynamic_shadow_ratio`：房屋遮陰率 (0.0 ~ 1.0)，隨太陽高度角與時間變化的建物陰影比例。
5. `dynamic_wbgt_c`：乾濕球溫度 (攝氏度 °C)，反映人體核心熱壓力。
6. `dynamic_uv_index`：紫外線指數 (UVI)，反映太陽直射曝曬威脅。
7. `dynamic_pm25_kriging`：PM2.5 濃度 (µg/m³)，透過空間克利金插值法算出的實時空污數據。

---

## 3. 模組化 Pipeline 架構設計
為確保系統具備高度的除錯性（Debuggability）與斷點續傳能力，本專案採取 **Pipeline 串聯架構**。每個模組皆為獨立運行的腳本，必須產出實體檔案，作為下一個模組的輸入源。

```
[原始路網] 
   │
   ▼
M1_data_validator.py  ──> 產出 M1_validated_network.graphml
   │
   ▼
M2_cost_calculator.py ──> 產出 M2_costed_network.graphml
   │
   ▼
M3_path_router.py     ──> 產出 M3_optimal_paths.json
   │
   ▼
M4_map_visualizer.py  ──> 產出 M4_routing_result_caseX.html
```

---

### 📁 模組一：M1_data_validator.py (資料檢查與預處理)
- **輸入**：原始大安區路網檔案（`data\Daan_Shaded_Network(還原)_dynamic_v1.graphml`）
- **核心任務**：
  1. 遍歷圖中所有的 Edges，嚴格檢查 7 個關鍵參數是否存在。
  2. **缺失值防呆補值 (Imputation)**：若發現特定路段缺少動態或靜態指標，應賦予合理的預設值（例如：以該批次資料的總平均值、或設定為最安全的基準值替代），確保程式不因 `None` 或 `NaN` 崩潰。
- **輸出**：`outputs/M1_validated_network.graphml`

---

### 📁 模組二：M2_cost_calculator.py (阻力成本計算核心)
- **輸入**：`outputs/M1_validated_network.graphml`
- **核心任務**：執行核心成本函數運算，並將計算出的通行成本寫回 Edge 屬性中。

#### 1. 指標預處理與截斷機制 (Clipping)
為防止極端異常值破壞數學邏輯（導致 Cost 出現負數或無限大），必須對各指標進行邊界截斷：
- 綠意遮陰率：$S_{green} = \min(\max(shading\_index, 0.0), 1.0)$ *(不進行傳統 Min-Max 正規化，但實施上限截斷，防範大於 1.0 的資料錯誤)*
- 房屋遮陰率：$S_{bldg} = \min(\max(dynamic\_shadow\_ratio, 0.0), 1.0)$
- 安全性：$Safety = \min(\max(safety\_score, 0.0), 1.0)$

#### 2. 熱壓力與空污正規化 (Normalization)
將不同單位的變數轉換為 0.0 ~ 1.0 的絕對阻力懲罰值：
- **乾濕球溫度 (WBGT)**：設定 20°C 為舒適無壓力起點，33°C 為極度危險極限。
  $$T_{norm} = \min\left(\max\left(\frac{dynamic\_wbgt\_c - 20}{33 - 20}, 0.0\right), 1.0\right)$$
- **紫外線 (UVI)**：基於 WHO 標準，以 11 級為極限危險。
  $$UV_{norm} = \min\left(\max\left(\frac{dynamic\_uv\_index}{11.0}, 0.0\right), 1.0\right)$$
- **空氣品質 (PM2.5)**：設定 50 µg/m³（普通等級上限）為懲罰滿分極限。
  $$PM_{norm} = \min\left(\max\left(\frac{dynamic\_pm25\_kriging}{50.0}, 0.0\right), 1.0\right)$$

#### 3. 環境熱壓力懲罰與遮陰緩解效應 ($P_{env}$)
結合靜態與動態遮陰計算綜合遮陰率 $S_{total}$（採用機率聯集避免空間重複計算）：
$$S_{total} = S_{green} + S_{bldg} - (S_{green} \times S_{bldg})$$

環境熱壓力 $P_{env}$ 由溫度與紫外線加權組成，並受到遮陰率的直接消減（遮陰作為熱壓力的緩解劑）：
$$P_{env} = (\alpha \cdot T_{norm} + \beta \cdot UV_{norm}) \times (1.0 - S_{total})$$
* **內部參數定義**：$\alpha = 0.8$ (WBGT 影響人體急性熱衰竭，權重較高), $\beta = 0.2$ (紫外線屬於次級曝曬防護)。

#### 4. 安全與空污懲罰
- 安全懲罰阻力：$P_{safe} = 1.0 - Safety$
- 空污懲罰阻力：$P_{air} = PM_{norm}$

#### 5. 總體成本函數與情境切換模式 (Scenario Modes)
最終道路通行成本公式整合如下：
$$Cost = length \times (1.0 + W_{env} \cdot P_{env} + W_{safe} \cdot P_{safe} + W_{air} \cdot P_{air})$$

為了評估參數敏感度，本模組需支援以下 **三種情境模式切換**（預設使用 Balanced Mode）：
1. **均衡通勤模式 (Balanced)**：`W_env = 1.0`, `W_safe = 1.0`, `W_air = 0.5`
2. **極端避暑模式 (Heat-Averse)**：`W_env = 2.0`, `W_safe = 0.5`, `W_air = 0.2`
3. **弱勢行人模式 (Safety-First)**：`W_env = 0.5`, `W_safe = 2.0`, `W_air = 0.5`

此外，需計算並新增一個消除長度干擾的指標 **單位距離成本 (Unit_Cost)** 以供視覺化使用：
$$Unit\_Cost = \frac{Cost}{length} = 1.0 + W_{env} \cdot P_{env} + W_{safe} \cdot P_{safe} + W_{air} \cdot P_{air}$$

- **輸出**：`outputs/M2_costed_network.graphml` (包含新增的 `cost` 與 `unit_cost` 屬性)

---

### 📁 模組三：M3_path_router.py (最佳路徑求解)
- **輸入**：`outputs/M2_costed_network.graphml`
- **核心任務**：調用 NetworkX 的 Dijkstra 演算法（指定以 `cost` 為權重），針對以下三個代表性情境進行路徑求解：
  - **Case 1 (跨校區通勤情境)**：
    - 起點 Node ID：`6240955569` (台大)
    - 終點 Node ID：`4266400151` (師大)
  - **Case 2 (生活消費與跨主幹道情境)**：
    - 起點 Node ID：`12263412046` (土研大樓)
    - 終點 Node ID：`5051817857` (永康街商圈)
  - **Case 3 (商圈跨區路徑情境)**：
    - 起點 Node ID：`5051817857` (永康街商圈)
    - 終點 Node ID：`5849716085` (東區)
- **輸出**：`outputs/M3_optimal_paths.json`（儲存三個 Case 的最佳路徑節點序列與對應的總長度、總成本數據）

---

### 📁 模組四：M4_map_visualizer.py (空間視覺化與網頁產出)
- **輸入**：`outputs/M2_costed_network.graphml` 與 `outputs/M3_optimal_paths.json`
- **核心任務**：利用 `folium` 套件建立具備高度科學嚴謹性、且支援多情境切換的互動式地圖。本模組需輸出單一 HTML 檔案，將所有視覺化成果整合於其中。

#### 視覺化核心規範與圖層設計：
1. **Phase 1 (全區阻力底圖 - 絕對分級機制)**：
   - **禁止直接使用 `cost` 進行分級渲染**，避免因路段長短造成視覺失真（長路永遠偏紅）。必須使用 `unit_cost`（單位距離成本）作為底圖渲染的基準。
   - **建立絕對分級（Fixed Colormap Bounds）**：為了能客觀呈現跨空間、跨時間點的熱壓力變遷趨勢，必須將 Colormap（如 `LinearColormap`）的色彩邊界完全鎖死。
     - 最低值 `vmin = 1.0`（綠色）：代表無任何環境與安全懲罰，極度舒適。
     - 最高值 `vmax = 3.0`（紅色）：代表面臨高額複合懲罰（極熱、無遮陰、不安全）。
   - 將整個大安區路網依照上述絕對分級規則繪製為 Folium 上的 PolyLine，作為最底層的環境脈絡。

2. **Phase 2 (多情境最佳路徑疊加與圖層控制)**：
   - 讀取 M3 輸出的最佳路徑 JSON 檔。
   - **圖層分組 (FeatureGroup)**：為 Case 1 (台大至師大)、Case 2 (土研至永康街) 與 Case 3 (永康至東區) 分別建立獨立的 `folium.FeatureGroup`。
   - **路徑樣式**：在各自的圖層中，以加粗、高對比色的線條（如 Case 1 用深藍色、Case 2 用深紫色、Case 3 用橘紅色，並加上 `weight=6`）繪製最佳步行路線。
   - 加上起點與終點的 Marker 標記。
   - 必須加入 `folium.LayerControl()`，讓使用者能在地圖右上角自由勾選、切換想觀看的路徑情境。

#### AI 腳本生成特別要求：
- **輸出**：`outputs/M4_routing_result.html`（單一可互動網頁，包含底圖與可切換的三個路徑圖層）。

---

## 4. Gemini SDK 醫療保健建議整合規範 (v2.1)
為了提升系統的實用價值，在 M3 階段求解完最佳路徑後，需擷取該路徑所行經的所有路段之環境指標，並調用 Gemini API 生成該路線專屬的醫療保健與戶外出行建議，最終在 M4 的互動式地圖中呈現。

### 數據擷取與加權平均要求：
- 對於最佳路徑上經過的所有路段，應以**路段長度為權重**計算以下指標的長度加權平均值：
  - 平均乾濕球溫度 (WBGT)
  - 平均綠意遮陰率
  - 平均建物陰影遮陰率
  - 平均細懸浮微粒 (PM2.5) 濃度
  - 平均紫外線指數
  - 平均交通安全得分
- 這些計算出的平均值需隨同路徑節點序列寫入 `outputs/M3_optimal_paths.json` 中。

### Gemini API 串接與提示詞 (Prompt) 規範：
- 讀取 `.env` 檔案中的 `GEMINI_API_KEY`。
- 採用 `requests` 庫直接發送 HTTP POST 請求至 Gemini 官方 API 端點：
  `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}`
- 提示詞需提供該路線在「均衡通勤模式 (Balanced)」下的長度加權平均指標值，並要求模型：
  1. 以繁體中文撰寫。
  2. 字數限制在 200 字以內。
  3. 分為「路段健康評估」與「防護出行建議」兩個小區塊。
  4. 針對高溫、空污或安全等特徵提出具體行為指導。
- 產出的建議文本需寫入 `outputs/M3_optimal_paths.json` 中的 `health_advice` 欄位。
- 系統必須實現**防崩潰與快取機制**：若 API 呼叫失敗（如無網路或 API Key 無效），應回退至本地預設之規則引擎建議；若輸入圖資與路徑未改變，應優先使用先前已產出的快取。

### 互動式地圖 (M4) 呈現規範：
- 當點擊地圖上的 Case 1、Case 2 或 Case 3 加粗路線（PolyLine）時，必須彈出氣泡視窗 (Popup) 展示該路線的 Gemini 建議。
- 地圖的起終點 Marker Popup 除了顯示原有的路徑長度與阻力成本外，亦需整合該建議（可使用美化的 CSS 卡片樣式呈現）。
