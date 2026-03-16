import requests
from bs4 import BeautifulSoup
import json
import os
import sys
import logging
import argparse
import random
from typing import Optional, List, Dict, Any
from time import sleep
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# HTTP 請求設定
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive"
}

# 爬蟲設定
SLEEP_INTERVAL = (0.5, 1.0)  # 爬蟲休息時間範圍（秒）
REQUEST_TIMEOUT = 10  # 請求逾時時間（秒）
MAX_RETRIES = 3  # 最多重試次數
BACKOFF_FACTOR = 0.5


def create_session_with_retries(
    retries: int = MAX_RETRIES,
    backoff_factor: float = BACKOFF_FACTOR
) -> requests.Session:
    """
    建立具備重試機制的 HTTP 工作階段。

    Args:
        retries: 最多重試次數
        backoff_factor: 重試延遲的退避因子

    Returns:
        具備重試機制的 requests.Session 物件
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"],
        backoff_factor=backoff_factor
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def fetch_anime_urls_to_scrape(engine) -> List[Dict[str, str]]:
    """
    查詢資料庫，獲取尚未爬取 metadata 的動畫 URL 清單。

    Args:
        engine: SQLAlchemy 引擎物件

    Returns:
        ['url': str, 'title': str] 字典列表
    """
    try:
        query = """
        SELECT 
            v.url,
            v.title
        FROM public.v_clean_tv_animelist v
        LEFT JOIN public.anime_metadata m ON v.url = m.url
        WHERE m.url IS NULL
        ORDER BY v.title ASC
        """
        with engine.connect() as conn:
            result = conn.execute(text(query))
            rows = result.fetchall()
            anime_list = [{"url": row[0], "title": row[1]} for row in rows]
        
        logger.info(f"查詢完成，共找到 {len(anime_list)} 部待爬取的動畫")
        return anime_list

    except SQLAlchemyError as e:
        logger.error(f"查詢資料庫失敗: {e}")
        raise


def parse_anime_metadata(
    url: str,
    session: requests.Session
) -> Optional[Dict[str, Any]]:
    """
    爬取動畫詳細頁面，解析代理廠商、製作廠商與分類標籤。

    Args:
        url: 動畫頁面 URL
        session: HTTP 工作階段

    Returns:
        {'agent': str|None, 'studio': str|None, 'tags': list} 字典，失敗則返回 None
    """
    try:
        response = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        logger.debug(f"成功獲取 {url}，狀態碼: {response.status_code}")

    except requests.exceptions.Timeout:
        logger.warning(f"請求逾時 (Timeout): {url}")
        return None
    except requests.exceptions.ConnectionError:
        logger.warning(f"連線失敗: {url}")
        return None
    except requests.exceptions.HTTPError as e:
        logger.warning(f"HTTP 錯誤 {response.status_code}: {url}")
        return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"未知的網路請求錯誤: {e}")
        return None

    try:
        soup = BeautifulSoup(response.content, 'html.parser')
        metadata = {
            "agent": _extract_agent(soup),
            "studio": _extract_studio(soup),
            "tags": _extract_tags(soup)
        }
        logger.debug(f"成功解析 {url}")
        return metadata

    except Exception as e:
        logger.warning(f"解析 HTML 時發生錯誤 ({url}): {e}")
        return None


def _extract_agent(soup: BeautifulSoup) -> Optional[str]:
    """
    從 HTML 中提取代理廠商資訊。

    頁面結構為：
    <li class="type">
        <span class="title">代理廠商</span>
        <p class="content">Ani-One</p>
    </li>
    """
    try:
        for li in soup.find_all('li', {'class': 'type'}):
            title_span = li.find('span', {'class': 'title'})
            if title_span and '代理廠商' in title_span.get_text(strip=True):
                content = li.find('p', {'class': 'content'})
                if content:
                    text = content.get_text(strip=True)
                    return text if text else None
        return None

    except Exception as e:
        logger.debug(f"提取代理廠商時出錯: {e}")
        return None


def _extract_studio(soup: BeautifulSoup) -> Optional[str]:
    """
    從 HTML 中提取製作廠商資訊。

    頁面結構為：
    <li class="type">
        <span class="title">製作廠商</span>
        <p class="content">動畫工房</p>
    </li>
    """
    try:
        for li in soup.find_all('li', {'class': 'type'}):
            title_span = li.find('span', {'class': 'title'})
            if title_span and '製作廠商' in title_span.get_text(strip=True):
                content = li.find('p', {'class': 'content'})
                if content:
                    text = content.get_text(strip=True)
                    return text if text else None
        return None

    except Exception as e:
        logger.debug(f"提取製作廠商時出錯: {e}")
        return None


def _extract_tags(soup: BeautifulSoup) -> List[str]:
    """
    從 HTML 中提取分類標籤。

    頁面結構為：
    <li class="type">
        <span class="title">作品分類</span>
        <ul class="tag-list">
            <li class="tag">親情</li>
            <li class="tag">偶像</li>
            <li class="tag">職場</li>
        </ul>
    </li>
    """
    tags = []

    try:
        for li in soup.find_all('li', {'class': 'type'}):
            title_span = li.find('span', {'class': 'title'})
            if title_span and '作品分類' in title_span.get_text(strip=True):
                tag_list = li.find('ul', {'class': 'tag-list'})
                if tag_list:
                    tag_items = tag_list.find_all('li', {'class': 'tag'})
                    tags = [item.get_text(strip=True) for item in tag_items]
                    tags = [t for t in tags if t]
                    return tags

        return tags

    except Exception as e:
        logger.debug(f"提取分類標籤時出錯: {e}")
        return tags


def save_metadata_to_db(
    metadata_list: List[Dict[str, Any]],
    engine
) -> int:
    """
    將爬取的 metadata 保存至資料庫。

    使用 PostgreSQL 的 ON CONFLICT 機制，若 URL 已存在則完全跳過。
    單條插入以確保異常時能精準定位失敗記錄。

    Args:
        metadata_list: metadata 字典列表
        engine: SQLAlchemy 引擎物件

    Returns:
        成功保存的記錄數
    """
    if not metadata_list:
        logger.info("沒有資料需要保存")
        return 0

    # PostgreSQL 原生 INSERT ... ON CONFLICT 語句
    insert_sql = """
    INSERT INTO public.anime_metadata (url, title, agent, studio, tags, updated_at)
    VALUES (:url, :title, :agent, :studio, CAST(:tags AS JSONB), CURRENT_TIMESTAMP)
    ON CONFLICT (url) DO NOTHING
    """

    saved_count = 0

    try:
        for item in metadata_list:
            try:
                # 為每條記錄單獨開啟事務，避免一個失敗導致整個事務 abort
                with engine.begin() as conn:
                    params = {
                        'url': item['url'],
                        'title': item['title'],
                        'agent': item['agent'],
                        'studio': item['studio'],
                        'tags': json.dumps(item['tags'], ensure_ascii=False),
                    }
                    conn.execute(text(insert_sql), params)
                    saved_count += 1
                    logger.debug(f"成功保存: {item['title']}")

            except SQLAlchemyError as e:
                logger.warning(f"保存單筆記錄失敗 ({item['title']}): {e}")
                continue

        logger.info(f"✅ 成功保存 {saved_count}/{len(metadata_list)} 筆 metadata 記錄")
        return saved_count

    except Exception as e:
        logger.error(f"資料庫寫入失敗: {e}")
        raise


def scrape_anime_metadata(
    db_url: str,
    dry_run: bool = False,
    limit: Optional[int] = None
) -> None:
    """
    主爬蟲流程：查詢、爬取、儲存動畫 metadata。

    Args:
        db_url: PostgreSQL 連線字串
        dry_run: 測試模式，不寫入資料庫
        limit: 限制爬取數量（用於測試）
    """
    # 建立資料庫連線
    try:
        engine = create_engine(db_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.commit()
        logger.info("資料庫連線成功")
    except SQLAlchemyError as e:
        logger.error(f"資料庫連線失敗: {e}")
        sys.exit(1)

    # 查詢待爬取的動畫 URL
    try:
        anime_list = fetch_anime_urls_to_scrape(engine)
    except Exception as e:
        logger.error(f"查詢 URL 清單失敗，程式終止: {e}")
        sys.exit(1)

    if not anime_list:
        logger.info("所有動畫 metadata 已爬取完成")
        engine.dispose()
        return

    # 考慮 limit 參數
    if limit:
        anime_list = anime_list[:limit]
        logger.info(f"限制爬取數量為 {limit}，實際將爬取 {len(anime_list)} 部")

    # 建立 HTTP 工作階段
    session = create_session_with_retries()
    metadata_list = []
    successful_count = 0
    failed_count = 0

    try:
        logger.info(f"開始爬取 {len(anime_list)} 部動畫的 metadata...")

        for idx, anime in enumerate(anime_list, 1):
            url = anime['url']
            title = anime['title']

            try:
                logger.info(f"[{idx}/{len(anime_list)}] 正在爬取: {title}")

                # 爬取頁面
                metadata = parse_anime_metadata(url, session)

                if metadata:
                    metadata['url'] = url
                    metadata['title'] = title
                    metadata_list.append(metadata)
                    successful_count += 1
                    logger.debug(f"✓ 成功爬取: {title}")
                else:
                    failed_count += 1
                    logger.warning(f"✗ 爬取失敗: {title}")

            except Exception as e:
                failed_count += 1
                logger.error(f"處理 {title} 時發生未預期的錯誤: {e}")

            # 隨機休息，避免被伺服器擋蔽
            if idx < len(anime_list):
                sleep_time = random.uniform(*SLEEP_INTERVAL)
                logger.debug(f"休息 {sleep_time:.2f} 秒...")
                sleep(sleep_time)

        logger.info(
            f"爬蟲完成 - 成功: {successful_count}, 失敗: {failed_count}"
        )

    except KeyboardInterrupt:
        logger.warning("使用者中斷爬蟲程式")
    finally:
        session.close()

    # 保存至資料庫
    if metadata_list and not dry_run:
        try:
            save_metadata_to_db(metadata_list, engine)
        except Exception as e:
            logger.error(f"保存 metadata 失敗: {e}")
            sys.exit(1)
    elif dry_run:
        logger.info(f"[DRY RUN] 將保存 {len(metadata_list)} 筆記錄（實際未保存）")
        for meta in metadata_list[:3]:  # 只顯示前 3 筆
            logger.info(f"  - {meta['title']}: {meta}")

    engine.dispose()
    logger.info("程式執行完成")


def main():
    """
    CLI 入口，支持自動化調度。
    """
    parser = argparse.ArgumentParser(
        description="爬取動畫瘋上的動畫 metadata（代理廠商、製作廠商、分類標籤）"
    )

    parser.add_argument(
        '--db-url',
        type=str,
        default=os.getenv(
            'DATABASE_URL',
            'postgresql://admin:password123@localhost:5432/anime_warehouse'
        ),
        help='PostgreSQL 連線字串 (預設: 環境變數 DATABASE_URL 或本地連線)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='測試模式，不寫入資料庫'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='限制爬取的動畫數量（用於測試，預設: 無限制）'
    )

    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='日誌等級'
    )

    args = parser.parse_args()

    # 設定日誌等級
    logger.setLevel(getattr(logging, args.log_level))

    logger.info("=" * 60)
    logger.info("動畫 Metadata 爬蟲程式")
    logger.info("=" * 60)
    logger.info(f"資料庫: {args.db_url.split('@')[-1] if '@' in args.db_url else 'Unknown'}")
    logger.info(f"測試模式: {args.dry_run}")
    if args.limit:
        logger.info(f"爬取限制: {args.limit} 部")
    logger.info("=" * 60)

    try:
        scrape_anime_metadata(
            db_url=args.db_url,
            dry_run=args.dry_run,
            limit=args.limit
        )
    except Exception as e:
        logger.error(f"致命錯誤: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
