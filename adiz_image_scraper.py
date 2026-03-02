#!/usr/bin/env python3
"""
國防部防空識別區(ADIZ)公告圖片爬蟲
爬取 https://www.mnd.gov.tw/news/plaactlist 目錄中的公告頁面圖片，
並儲存至指定資料夾。
"""

import os
import re
import time
import argparse
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


# 請求間隔（秒），避免對伺服器造成壓力
REQUEST_DELAY = 1.0

# 預設儲存目錄
DEFAULT_OUTPUT_DIR = "adiz_images"

# 請求標頭，模擬一般瀏覽器
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}


def sanitize_filename(name: str) -> str:
    """將字串轉為安全的檔名"""
    # 移除或替換不適合作為檔名的字元
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = name.strip().strip(".")
    return name[:200] if len(name) > 200 else name or "unnamed"


def get_session() -> requests.Session:
    """建立帶有標頭的 requests Session"""
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def get_article_links(
    session: requests.Session, list_url: str, max_pages: int = None, delay: float = REQUEST_DELAY
) -> list[str]:
    """
    從目錄頁面取得所有公告文章的連結
    國防部網站以 JavaScript 動態載入，使用正則從 HTML 擷取 news/plaact/ID
    分頁格式：plaactlist/1, plaactlist/2, plaactlist/3 ...
    """
    base_url = "https://www.mnd.gov.tw/"
    # 正規化目錄 URL（移除尾端斜線，供分頁拼接）
    list_url_base = list_url.rstrip("/")
    article_links = []
    page = 1

    while True:
        if page == 1:
            page_url = list_url_base
        else:
            # 國防部分頁使用 plaactlist/2, plaactlist/3 格式
            page_url = f"{list_url_base}/{page}"

        try:
            resp = session.get(page_url, timeout=15, verify=False)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
        except requests.RequestException as e:
            print(f"  [錯誤] 取得目錄頁失敗 (頁面 {page}): {e}")
            break

        # 使用正則擷取 news/plaact/ID（因頁面可能為 JS 動態產生）
        ids = re.findall(r"news/plaact/(\d+)", resp.text)
        seen = {url.rstrip("/").split("/")[-1] for url in article_links}
        added = 0
        for aid in ids:
            if aid not in seen:
                seen.add(aid)
                article_links.append(urljoin(base_url, f"news/plaact/{aid}"))
                added += 1

        if not added:
            break

        page += 1
        if max_pages and page > max_pages:
            break

        time.sleep(delay)

    return article_links


def get_images_from_article(session: requests.Session, article_url: str) -> list[tuple[str, str]]:
    """
    從單一公告頁面取得所有圖片 URL 與其 alt 描述
    回傳: [(image_url, alt_or_filename), ...]
    """
    base_url = "https://www.mnd.gov.tw"
    images = []

    try:
        resp = session.get(article_url, timeout=15, verify=False)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
    except requests.RequestException as e:
        print(f"  [錯誤] 無法取得頁面 {article_url}: {e}")
        return images

    soup = BeautifulSoup(resp.text, "html.parser")

    # 排除的 UI 元素路徑關鍵字
    skip_patterns = [
        "banner", "icon", "logo", "decoration", "deco", "button", "arrow",
        "spacer", "pixel", "1x1", "service-icon", "sec02_deco",
        "/img/", "/Img/",  # 網站通用資源
        "menu.svg", "search", "sitemap", "fontsize", "language",
        "sun.svg", "moon.svg", "facebook", "line.svg", "x.svg", "link.svg",
        "print.svg", "hamburger",
    ]

    # 優先保留：防空識別區示意圖、臺海周邊、NewUpload
    content_keywords = ["newupload", "臺海", "台海", "周邊", "空域", "示意圖", "活動"]

    def is_content_image(src: str, alt: str) -> bool:
        combined = (src + " " + alt).lower()
        return any(kw in combined for kw in content_keywords)

    def should_skip(src: str) -> bool:
        src_lower = src.lower()
        return any(p in src_lower for p in skip_patterns)

    # 尋找所有 img 標籤
    for img in soup.find_all("img", src=True):
        src = img["src"].strip()
        if should_skip(src):
            continue

        full_url = urljoin(base_url, src)
        parsed = urlparse(full_url)
        if "mnd.gov.tw" not in parsed.netloc and "gpwb.gov.tw" not in parsed.netloc and "gov.tw" not in parsed.netloc:
            continue

        alt = (img.get("alt") or "").strip() or ""
        # 若明確為內容圖則加入；否則僅在路徑含 NewUpload 時加入（排除一般 /img/ 資源）
        if is_content_image(src, alt):
            images.append((full_url, alt))
        elif "newupload" in full_url.lower() or "/newupload/" in full_url.lower():
            images.append((full_url, alt))
        elif "/img/" in full_url.lower() or full_url.rstrip("/").endswith(".svg"):
            # 排除未明確為內容的 svg 及 /img/ 資源
            continue
        else:
            images.append((full_url, alt))

    # 檢查附件、下載連結（常為防空識別區示意圖）
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        href_lower = href.lower()
        if not any(href_lower.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"]):
            continue
        full_url = urljoin(base_url, href)
        if "mnd.gov.tw" not in full_url and "gpwb.gov.tw" not in full_url:
            continue
        text = (a.get_text() or "").strip()[:80]
        if "下載" in text or "台海" in text or "臺海" in text or "示意" in text or "newupload" in full_url.lower():
            images.append((full_url, text))

    # 以 URL 去重，保留第一次出現的 (url, alt)
    seen_urls = set()
    unique_images = []
    for url, alt in images:
        if url not in seen_urls:
            seen_urls.add(url)
            unique_images.append((url, alt))
    return unique_images


def download_image(session: requests.Session, url: str, save_path: Path) -> bool:
    """下載單一圖片並儲存"""
    try:
        resp = session.get(url, timeout=30, stream=True, verify=False)
        resp.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"    [錯誤] 下載失敗 {url}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="爬取國防部防空識別區公告圖片"
    )
    parser.add_argument(
        "-o", "--output",
        default=DEFAULT_OUTPUT_DIR,
        help=f"圖片儲存目錄 (預設: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--list-url",
        default="https://www.mnd.gov.tw/news/plaactlist",
        help="目錄頁面 URL",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=20,
        help="最多爬取幾頁目錄 (預設: 20)",
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=None,
        help="最多爬取幾則公告 (預設: 全部)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=REQUEST_DELAY,
        help=f"請求間隔秒數 (預設: {REQUEST_DELAY})",
    )
    args = parser.parse_args()
    delay = args.delay

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"圖片將儲存至: {output_dir.absolute()}")

    session = get_session()

    # 1. 取得文章連結
    print("\n[1/2] 正在取得公告文章連結...")
    article_links = get_article_links(session, args.list_url, args.max_pages, delay)

    if args.max_articles:
        article_links = article_links[: args.max_articles]

    print(f"  找到 {len(article_links)} 則公告")

    if not article_links:
        print("  未找到任何文章連結，請檢查目錄頁 URL 或網站結構是否變更。")
        return

    # 2. 逐一爬取每則公告的圖片
    print("\n[2/2] 正在爬取並下載圖片...")
    total_downloaded = 0

    for i, url in enumerate(article_links, 1):
        # 從 URL 取得文章 ID 作為子目錄名稱
        match = re.search(r"/plaact/(\d+)", url)
        article_id = match.group(1) if match else str(i)
        article_dir = output_dir / article_id
        article_dir.mkdir(parents=True, exist_ok=True)

        images = get_images_from_article(session, url)
        print(f"  [{i}/{len(article_links)}] {url} - 發現 {len(images)} 張圖片")

        for j, (img_url, alt) in enumerate(images):
            ext = Path(urlparse(img_url).path).suffix or ".jpg"
            if not ext.startswith("."):
                ext = "." + ext
            safe_alt = sanitize_filename(alt)[:50] if alt else ""
            filename = f"{j:03d}_{safe_alt}{ext}" if safe_alt else f"{j:03d}{ext}"
            save_path = article_dir / filename

            if save_path.exists():
                print(f"    略過 (已存在): {filename}")
                total_downloaded += 1
                continue

            if download_image(session, img_url, save_path):
                print(f"    已儲存: {filename}")
                total_downloaded += 1

        time.sleep(delay)

    print(f"\n完成！共下載 {total_downloaded} 張圖片至 {output_dir.absolute()}")


if __name__ == "__main__":
    main()
