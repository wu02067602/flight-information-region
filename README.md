# 國防部防空識別區 (ADIZ) 圖片爬蟲

從 [國防部區域動態列表](https://www.mnd.gov.tw/news/plaactlist) 爬取公告中的防空識別區示意圖，並儲存至本機資料夾。

## 安裝

```bash
pip install -r requirements.txt
```

## 使用方式

### 基本用法（爬取目錄中所有公告的防空識別區圖片）

```bash
python adiz_image_scraper.py
```

圖片預設儲存於 `adiz_images/` 資料夾，依文章 ID 分子目錄。預設爬取目錄前 20 頁的公告。

### 指定輸出目錄

```bash
python adiz_image_scraper.py -o 我的圖片資料夾
```

### 限制爬取數量（測試用）

```bash
# 只爬取前 3 則公告
python adiz_image_scraper.py --max-articles 3

# 只爬取目錄第 1 頁
python adiz_image_scraper.py --max-pages 1
```

### 調整請求間隔

```bash
# 每次請求間隔 2 秒，降低對伺服器負擔
python adiz_image_scraper.py --delay 2
```

## 參數說明

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `-o`, `--output` | 圖片儲存目錄 | `adiz_images` |
| `--list-url` | 目錄頁面 URL | `https://www.mnd.gov.tw/news/plaactlist` |
| `--max-pages` | 最多爬取幾頁目錄 | 20 |
| `--max-articles` | 最多爬取幾則公告 | 全部 |
| `--delay` | 請求間隔（秒） | 1.0 |

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

## 注意事項

- 請勿過度頻繁請求，建議使用 `--delay 1` 或更高
- 爬蟲僅下載與防空識別區、臺海周邊空域相關的圖片，排除網站 UI 圖示
- 若網站結構變更，可能需要更新爬蟲邏輯
