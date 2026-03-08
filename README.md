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
