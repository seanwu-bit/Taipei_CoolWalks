# ☀️ Dynamic Shadow & Microclimate
### 台北市大安區 動態陰影與微氣候分析系統

> 國立臺灣大學 115-2 學期專題  
> 工程師角色：動態陰影與微氣候工程師 (Dynamic Shadow & Microclimate)

---

## 📁 需要提供的檔案清單

接收者需要取得以下 **4 個必要 Python 程式檔**、**1 個選配測試檔** 與 **1 個建物 Shapefile 資料夾**：

```
📦 分享包
├── Solar_Geometry/
│   ├── solar_engine.py        ← Task 1：太陽幾何演算核心
│   ├── shadow_engine.py       ← Task 2：建物動態陰影投影
│   ├── weather_engine.py      ← Task 4：中央氣象署 API 介接
│   ├── visualize_solar.py     ← Streamlit 視覺化儀表板（主程式）
│   └── test_solar_engine.py   ← 單元測試（選擇性提供）
│
└── Daan_Buildings/            ← 必須一併提供的空間資料
    ├── Buildings_Daan.shp
    ├── Buildings_Daan.dbf
    ├── Buildings_Daan.shx
    ├── Buildings_Daan.prj
    ├── Buildings_Daan.cpg
    ├── Buildings_Daan.sbn
    ├── Buildings_Daan.sbx
    └── Buildings_Daan.shp.xml
```

> ⚠️ **注意**：`Daan_Buildings/` 資料夾與 `Solar_Geometry/` 資料夾的**相對路徑關係**必須維持，  
> 即兩者放在同一個上層目錄下。詳見下方目錄結構說明。

---

## 🗂️ 建議目錄結構

收到檔案後，請依照以下結構擺放：

```
你的專案資料夾/
├── Solar_Geometry/
│   ├── solar_engine.py
│   ├── shadow_engine.py
│   ├── weather_engine.py
│   ├── visualize_solar.py
│   └── test_solar_engine.py
│
└── Daan_Buildings/
    └── Buildings_Daan.shp  （及其他 .dbf .shx .prj 等）
```

---

## 🐍 環境需求

- **Python 3.10 或以上**
- 作業系統：Windows / macOS / Linux 皆可

---

## ⚙️ 安裝步驟

### Step 1｜確認 Python 版本

```bash
python --version
# 應顯示 Python 3.10.x 或更新版本
```

### Step 2｜安裝所需套件

開啟終端機（PowerShell / Terminal），執行：

```bash
pip install pysolar==0.13 geopandas==1.1.3 shapely==2.1.2 pyproj==3.7.1 streamlit==1.57.0 plotly==6.7.0 folium==0.20.0 streamlit-folium==0.26.2 requests==2.32.4 pandas==2.3.1 numpy==2.2.6
```

或建立 `requirements.txt` 後一次安裝：

**`requirements.txt`**
```
pysolar==0.13
geopandas==1.1.3
shapely==2.1.2
pyproj==3.7.1
streamlit==1.57.0
plotly==6.7.0
folium==0.20.0
streamlit-folium==0.26.2
requests==2.32.4
pandas==2.3.1
numpy==2.2.6
```

### Task 4 補充：AQI / PM2.5

- `weather_engine.py` 已補充環境部 `AQX_P_432` 空品資料（AQI / PM2.5）
- 會顯示最近測站的 AQI、PM2.5，以及以大安區中心點估算的 `PM2.5 Kriging` 平滑值
- Kriging 採內建 ordinary kriging，小樣本或矩陣退化時自動 fallback 到 IDW
- 若環境部 API 需要金鑰，可先設定環境變數 `MOENV_API_KEY`

```powershell
$env:MOENV_API_KEY="your-moenv-api-key"
streamlit run visualize_solar.py
```

```bash
pip install -r requirements.txt
```

### Step 3｜確認資料夾結構

請確認目錄結構如下，**不需手動修改 `SHP_PATH`**：
```
你的專案資料夾/
├── Solar_Geometry/
│   ├── solar_engine.py
│   ├── shadow_engine.py
│   ├── weather_engine.py
│   ├── visualize_solar.py
│   └── test_solar_engine.py
│
└── Daan_Buildings/
    └── Buildings_Daan.shp  （及其他 .dbf .shx .prj 等）
```

---

## 🚀 啟動儀表板

進入 `Solar_Geometry/` 資料夾後執行：

```bash
cd Solar_Geometry
streamlit run visualize_solar.py
```

瀏覽器會自動開啟，或手動前往：

```
http://localhost:8501
```

---

## 🖥️ 儀表板功能說明

### 側邊欄（左側控制面板）

| 控制項 | 說明 |
|---|---|
| 使用目前時間 | 自動帶入現在時間 |
| 出發日期 / 時間 | 手動設定模擬時間（UTC+8） |
| 步行時間（分鐘） | 設定步行總時長，15–90 分鐘 |
| 計算間隔 | 每 15 或 30 分鐘計算一個時間分片 |
| 全日太陽軌跡 | 開關全日高度角弧線圖 |

---

### 🌞 Task 1 — 太陽幾何演算核心

計算大安區中心在指定出發時間的太陽位置，並依步行時間產生多個時間分片。

**主要視覺化：**
- 出發時刻高度角、方位角、UTC 時間等 KPI 卡片
- 步行期間太陽高度角折線圖
- 步行期間太陽方位角折線圖
- 太陽方位角羅盤（極座標圖）
- 全日高度角弧線（含步行窗口標示）
- 大安區地圖 + 太陽方位射線（各時間切片）
- 時間分片計算結果資料表

---

### 🏙️ Task 2 — 動態建物陰影投影

依據太陽位置與大安區 19,674 棟建物高度，計算每棟建物的地面陰影並合併為總遮罩。

**陰影公式：**

$$L = \frac{H}{\tan(\theta)}$$

- $L$：陰影長度（公尺）
- $H$：建物高度（`BUILD_H` 欄位，公尺）
- $\theta$：太陽高度角（弧度）

**幾何作法：**
- 建物底圖 `footprint` 依陰影向量進行平移
- 以原始 polygon、平移後 polygon 與中間掃掠四邊形共同組成**完整陰影多邊形**
- 最後以 `Unary Union` 合併所有建物陰影，得到全區總遮罩

**操作步驟：**
1. 點選 **🏙️ Task 2** 頁籤
2. 使用 **「選擇時間切片」** Slider 選擇要檢視的時刻
3. 點擊 **🔄 計算陰影** 按鈕（首次進入須計算，約需數秒）
4. 切換「顯示 Unary Union 總遮罩」/ 「顯示建物底圖」開關調整圖層

**主要視覺化：**
- 互動地圖：紅色虛線建物輪廓 + 深藍色陰影總遮罩 + 太陽方位箭頭
- 各時刻陰影統計對比表（投影棟數、平均陰影長度）
- 平均陰影長度柱狀圖
- 投影建物數全時段趨勢圖

---

### 🌡️ Task 4 — 即時氣象 & 微氣候

即時串接中央氣象署開放資料，取得臺北站觀測數值並計算衍生微氣候指標。

> **需要網路連線** 才能正常取得 CWA API 資料。

**資料來源：**

| API 端點 | 資料內容 |
|---|---|
| `O-A0001-001` | 臺北站（466920）即時氣溫、濕度、風速、降雨 |
| `O-A0005-001` | 臺北站當日 UV 指數最大值 |
| `F-C0032-001` | 台北市 36hr 天氣預報、降雨機率 |

**衍生指標：**

| 指標 | 說明 |
|---|---|
| 體感溫度 | Steadman 公式，考量氣溫、濕度、風速 |
| 熱指數 | Rothfusz 迴歸（T ≥ 27°C 時啟用） |
| WBGT | 濕球黑球溫度，依 ISO 7933 危害分級 |
| 陰影加權倍率 | UV + WBGT 綜合計算，供路徑演算成本函數使用 |

**操作：** 點選 **🌡️ Task 4** 頁籤，按 **🔄 刷新氣象** 取得最新資料。

---

## 🧪 執行單元測試（選擇性）

```bash
cd Solar_Geometry
pip install pytest
pytest test_solar_engine.py -v
# 預期結果：23 passed
```

---

## 📦 各檔案功能對照

| 檔案 | 功能 | 是否必要 |
|---|---|---|
| `solar_engine.py` | Task 1 核心：Pysolar 太陽位置計算、時間分片 | ✅ 必要 |
| `shadow_engine.py` | Task 2 核心：建物陰影投影、Shapely Unary Union | ✅ 必要 |
| `weather_engine.py` | Task 4 核心：CWA API 串接、WBGT/熱指數計算 | ✅ 必要 |
| `visualize_solar.py` | Streamlit 主程式，整合以上三個模組 | ✅ 必要 |
| `test_solar_engine.py` | solar_engine 單元測試（pytest） | 選擇性 |
| `Daan_Buildings/` | 建物高度與幾何資料（EPSG:3826） | ✅ 必要 |

---

## ❓ 常見問題

**Q：執行後瀏覽器沒有自動開啟？**  
A：手動前往 `http://localhost:8501`

**Q：出現 `FileNotFoundError` 關於 `.shp` 檔？**  
A：請確認 `Daan_Buildings/` 與 `Solar_Geometry/` 位於同一層目錄，且 `Daan_Buildings/` 內包含完整的 `.shp/.dbf/.shx/.prj` 等檔案。
