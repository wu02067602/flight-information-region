# 國防部防空識別區 (ADIZ) 圖片座標抽取專案

從 [國防部區域動態列表](https://www.mnd.gov.tw/news/plaactlist) 爬取公告中的防空識別區示意圖，並自動抽取紅框座標與表格文字入庫。

## 安裝

```bash
pip install -r requirements.txt
```

## 環境設定

- **資料庫**：需 PostgreSQL + PostGIS。先建立資料庫並啟用 PostGIS，再設定環境變數：
  ```bash
  createdb adiz
  psql adiz -c "CREATE EXTENSION IF NOT EXISTS postgis;"
  export ADIZ_DATABASE_URL="postgresql://user:pass@localhost:5432/adiz"
  ```
- **管線版本**：`ADIZ_PIPELINE_VERSION`（預設 `v1.0`），重跑時可區分結果版本。

## 使用方式

### 1. 爬取圖片（沿用既有爬蟲）

```bash
python adiz_image_scraper.py
```

圖片預設儲存於 `adiz_images/<article_id>/`，檔名如 `000.jpg`、`001_xxx.svg`。

### 2. 初始化資料庫

```bash
python scripts/init_db.py
```

### 3. 執行座標抽取管線

```bash
python adiz_extract.py
```

- `-i, --images-dir`：圖片目錄（預設 `adiz_images`）
- `--no-resume`：強制重跑，不略過已處理
- `--max-images N`：最多處理 N 張（測試用）
- `-v`：詳細日誌

### 4. 查詢與報告

```bash
# 低信心清單（供人工覆核）
python scripts/query_low_confidence.py

# 處理報告（成功率、失敗率、失敗類型）
python scripts/report.py
```

## 輸出結構

```
adiz_images/
├── 86214/          # 文章 ID
│   ├── 000.jpg     # 防空識別區示意圖
│   └── 001_xxx.svg
├── 86209/
│   └── 000_xxx.svg
└── ...
```

## 資料模型

- **raw_images**：來源 URL、article_id、檔案路徑、處理狀態
- **detections**：紅框像素/經緯度幾何、OCR 原文、信心分數
- **events**：業務欄位（時間、機型、架次、備註、geometry）、審核狀態

## 爬蟲參數說明

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `-o`, `--output` | 圖片儲存目錄 | `adiz_images` |
| `--list-url` | 目錄頁面 URL | `https://www.mnd.gov.tw/news/plaactlist` |
| `--max-pages` | 最多爬取幾頁目錄 | 20 |
| `--max-articles` | 最多爬取幾則公告 | 全部 |
| `--delay` | 請求間隔（秒） | 1.0 |

## 注意事項

- 請勿過度頻繁請求，建議使用 `--delay 1` 或更高
- 爬蟲僅下載與防空識別區、臺海周邊空域相關的圖片，排除網站 UI 圖示
- SVG 圖檔需安裝 `cairosvg` 才能處理
- OCR 使用 PaddleOCR，首次執行會下載模型
