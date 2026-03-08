# 國防部防空識別區 (ADIZ) 圖片座標抽取專案

從 [國防部區域動態列表](https://www.mnd.gov.tw/news/plaactlist) 爬取公告中的防空識別區示意圖，並**自動抽取紅色活動區塊座標**與**左上角表格文字**，寫入 BigQuery 供查詢與稽核。

## 專案結構

```
.
├── adiz_image_scraper.py   # 既有爬蟲：下載圖片至 adiz_images/
├── run_pipeline.py         # 管線入口：紅框偵測、OCR、座標轉換、入庫
├── adiz_pipeline/          # 管線模組
│   ├── config.py           # 設定（ROI、校正點、信心門檻）
│   ├── image_loader.py     # 圖片載入、SVG rasterize
│   ├── red_detector.py     # OpenCV 紅框偵測
│   ├── coordinate_converter.py  # 像素→經緯度
│   ├── ocr_gemini.py       # Gemini OCR、表格結構化
│   ├── association.py      # 紅框與表格關聯
│   ├── bigquery_schema.py  # 資料表結構
│   ├── bigquery_loader.py  # 載入邏輯
│   └── pipeline.py         # 主流程
├── adiz_images/            # 圖片目錄（依 article_id 分子目錄）
├── requirements.txt
└── .env.example
```

## 安裝

```bash
pip install -r requirements.txt
cp .env.example .env
# 編輯 .env 填入 GEMINI_API_KEY、BQ_PROJECT
```

## 使用方式

### 1. 爬取圖片（既有功能）

```bash
python adiz_image_scraper.py
```

圖片儲存於 `adiz_images/<article_id>/000.jpg` 等。

### 2. 執行座標抽取管線

```bash
# 完整執行（寫入 BigQuery）
python run_pipeline.py

# 僅處理前 5 張圖、不寫入 BigQuery（測試用）
python run_pipeline.py --max-images 5 --no-bigquery

# 指定圖片目錄與報告輸出
python run_pipeline.py -i adiz_images --report report.json
```

### 3. 管線參數

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `-i`, `--images-dir` | 圖片根目錄 | `adiz_images` |
| `--run-id` | 批次 ID（重跑追蹤） | 自動 UUID |
| `--pipeline-version` | 管線版本 | `0.1.0` |
| `--max-images` | 最多處理幾張圖 | 全部 |
| `--no-bigquery` | 不寫入 BigQuery | False |
| `--report` | 報告輸出 JSON 路徑 | - |

## 環境變數

| 變數 | 說明 | 必填 |
|------|------|------|
| `GEMINI_API_KEY` | Google AI API Key（OCR） | 是 |
| `BQ_PROJECT` | BigQuery 專案 ID | 入庫時 |
| `BQ_DATASET` | BigQuery 資料集 | `adiz` |
| `ADIZ_IMAGES_DIR` | 圖片目錄 | `adiz_images` |
| `GEMINI_MODEL` | Gemini 模型 | `gemini-1.5-flash` |

## 資料模型（BigQuery）

- **raw_images**：來源圖片追蹤、處理狀態
- **detections**：紅框偵測結果（像素多邊形、地理幾何、OCR 原文、信心分數）
- **events**：業務事件（項次、時間、機型、架次、備註、geometry）
- **ocr_error_queue**：低信心/失敗樣本，供人工覆核

## 驗收對應

| 需求 | 實作 |
|------|------|
| 讀取 adiz_images 批次處理 | `discover_images()` + `run_batch()` |
| 紅框偵測、多邊形頂點 | `red_detector.detect_red_regions()` |
| 像素→經緯度 | `coordinate_converter.pixel_to_geography()` |
| 左上角表格 OCR | `ocr_gemini.extract_table_ocr()` |
| 紅框與表格關聯 | `association.associate_polygons_to_rows()` |
| 寫入 BigQuery | `bigquery_loader` |
| 信心分數、覆核清單 | `review_status`、`ocr_error_queue` |
| run_id、pipeline_version 追蹤 | 全表支援 |
| 可中斷續跑 | 依 source_id 可重跑同一批 |

## 注意事項

- 校正點（`DEFAULT_CALIBRATION_POINTS`）需依實際圖檔版型調整
- 紅框偵測參數（HSV、面積門檻）可於 `config.py` 微調
- 若無 BigQuery 憑證，使用 `--no-bigquery` 可僅產出報告

---

## 開發過程與研究記錄

### 功能擴充（紅線經緯度與文字對應）

在既有紅框偵測基礎上，新增：

- **線段偵測**：紅色實線／虛線路徑，輸出 `LINESTRING` 經緯度
- **標點偵測**：紅色圓形標記（①②③④⑤），與線段關聯
- **關聯邏輯**：標點 ↔ 線段 ↔ OCR 表格列（`line_text`）

### 名詞定義（人工標註用）

| 名詞 | 定義 |
|------|------|
| **多邊形** | 紅色實心框線圍成的封閉區域（矩形），如活動區 ①②③ |
| **線段** | 紅色實線或虛線路徑（航線、氣球軌跡等） |
| **標點** | 地圖上紅色圓形標記，通常帶編號 ④⑤ |
| **Detection** | 多邊形數 + 線段數（標點不單獨計入） |

### 研究發現（效果不佳原因）

1. **多邊形漏檢**：面積門檻過高、圓形度排除圓角矩形、輪廓近似後頂點不足
2. **線段誤檢**：多邊形偵測失敗時，邊框被 Hough 當成線段
3. **標點漏檢**：與多邊形重疊、圓形度門檻過嚴

### 參數調適摘要

| 類別 | 主要調整 |
|------|----------|
| HSV | `RED_SAT_MIN` 35、`RED_VAL_MIN` 90（實圖紅色偏淡） |
| 多邊形 | `MIN_POLYGON_AREA` 180、`MAX_POLYGON_CIRCULARITY` 0.88、NMS 重疊過濾 |
| 線段 | `MIN_LINE_LENGTH` 130、`MIN_PATH_LENGTH` 100、排除多邊形/標點、`LINE_ROI_LEFT` 0.32 |
| 標點 | `MIN_MARKER_AREA` 25、`MIN_MARKER_CIRCULARITY` 0.28 |
| ROI | `MAP_ROI_TOP` 0.28、線段偵測排除左側表格區 |

### 測試結果（exmpel 23 張，人工標註對照）

| 圖片 | 多邊形 | 線段 | 標點 | Detection | 人工標註 |
|------|:------:|:----:|:----:|:---------:|:--------:|
| 84835 | 2 | 2 | 4 | 4 | 3/0/6 |
| 84840 | 2 | 0 | 7 | 2 | 3/0/6 |
| 84844 | 2 | 0 | 6 | 2 | 3/0/6 |
| 84846 | 1 | 2 | 6 | 3 | 2/0/4 |
| 84850 | 2 | 0 | 5 | 2 | 1/0/2 |
| 84852 | 1 | 2 | 2 | 3 | 2/0/4 |
| 84854 | 1 | 1 | 6 | 2 | 2/0/4 |
| 84857 | 3 | 0 | 9 | 3 | 2/0/4 |
| 84863 | 0 | 2 | 6 | 2 | 3/0/6 |
| 84866 | 1 | 1 | 1 | 2 | 1/0/2 |
| 84869 | 1 | 1 | 2 | 2 | 2/0/4 |
| 84876 | 1 | 0 | 1 | 1 | 1/0/2 |
| 84881 | 2 | 0 | 2 | 2 | 2/0/4 |
| 84884 | 2 | 1 | 11 | 3 | 3/0/6 |
| 84889 | 2 | 0 | 2 | 2 | 2/0/4 |
| 84891 | 3 | 1 | 3 | 4 | 2/0/4 |
| 84894 | 3 | 0 | 13 | 3 | 3/0/6 |
| 84896 | 5 | 0 | 15 | 5 | 4/0/8 |
| 84900 | 4 | 4 | 16 | 8 | 4/0/8 |
| 84905 | 4 | 0 | 7 | 4 | 3/0/6 |
| 86194 | 0 | 1 | 0 | 1 | 1/0/2 |
| 86205 | 2 | 0 | 6 | 2 | 3/0/6 |
| 86248 | 3 | 1 | 11 | 4 | 3/2/12 |

**彙總**：總 Detection 66、總誤差 |pred-gt| 為 poly=18、line=19、marker=57。多邊形與線段皆正確者：84876、84881、84889、84894。

**測試指令**：`python test_pipeline_on_examples.py`（使用 exmpel 目錄）
