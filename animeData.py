import pandas as pd
import numpy as np
import requests
import xml.etree.ElementTree as ET
import html
import re
import os
import sys
import logging
from sqlalchemy import create_engine, text, MetaData
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.dialects.postgresql import insert
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from time import sleep

# 設定日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

url = "https://ani.gamer.com.tw/sitemap/sitemap.xml"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Safari/537.36"
    ),  
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive"
}

# 設定重試策略
def create_session_with_retries(retries=3, backoff_factor=0.5):
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

# 7. 定義 Upsert 函數
def save_to_db_upsert(df, table_name, engine):
    """
    實現 Upsert：如果資料已存在（loc 衝突），則更新觀看數、評分等欄位。
    使用逐筆 Upsert（避免批量插入時的衝突問題）。
    """
    # 將 DataFrame 轉為字典清單，將所有 NaN 轉換為 None
    data = df.replace({np.nan: None}).to_dict(orient='records')
    
    if not data:
        logger.warning("沒有資料需要寫入")
        return
    
    # 使用 MetaData 反射獲取表定義
    metadata = MetaData()
    metadata.reflect(bind=engine)
    tbl = metadata.tables[table_name]
    
    upserted_count = 0
    
    # 逐筆進行 Upsert（每條記錄單獨開啟事務）
    for row_data in data:
        try:
            stmt = insert(tbl).values([row_data])
            
            # 定義更新邏輯：除了主鍵 (loc) 以外，其他欄位都更新為最新抓到的值
            update_columns = {
                col: stmt.excluded[col] 
                for col in df.columns if col != 'loc'
            }
            
            # 建立 ON CONFLICT 語句
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=['loc'], # 衝突判斷基準
                set_=update_columns      # 更新內容
            )
            
            with engine.begin() as conn:
                conn.execute(upsert_stmt)
            upserted_count += 1
            
        except SQLAlchemyError as e:
            logger.warning(f"單筆 Upsert 失敗 ({row_data.get('loc')}): {e}")
            continue
    
    logger.info(f"✅ 成功完成 {upserted_count}/{len(data)} 筆資料的 Upsert 作業！")


def scrape_anime_data():
    """
    主爬蟲流程：從 Sitemap 爬取動畫資料並寫入資料庫。
    """
    # 獲取 XML 數據
    try:
        logger.info("開始爬取動畫資料...")
        session = create_session_with_retries()
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info(f"成功獲取 Sitemap，狀態碼: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"網路請求失敗: {e}")
        sys.exit(1)

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as e:
        logger.error(f"XML 解析失敗: {e}")
        sys.exit(1)

    data = []
    error_count = 0

    for url_node in root.findall(".//{*}url"):      # .//表搜尋當前節點往下的所有層級   {*}不管 namespace 是什麼
        try:
            loc = url_node.find("{*}loc")
            changefreq = url_node.find("{*}changefreq")
            
            video_node = url_node.find("{*}video")
            
            if video_node is not None:
                title = video_node.find("{*}title")
                pub_date = video_node.find("{*}publication_date")
                rating = video_node.find("{*}rating")
                duration = video_node.find("{*}duration")
                view_count = video_node.find("{*}view_count")
                restriction = video_node.find("{*}restriction")
                
                # 數據驗證與類型轉換
                try:
                    video_rating = float(rating.text) if rating is not None and rating.text else None
                except (ValueError, TypeError):
                    video_rating = None
                
                try:
                    video_duration = int(duration.text) if duration is not None and duration.text else None
                except (ValueError, TypeError):
                    video_duration = None
                
                try:
                    video_view_count = int(view_count.text) if view_count is not None and view_count.text else None
                except (ValueError, TypeError):
                    video_view_count = None
                
                data.append({
                    "loc": loc.text if loc is not None else None,
                    "changefreq": changefreq.text if changefreq is not None else None,
                    "video_title": title.text if title is not None else None,
                    "video_publication_date": pub_date.text if pub_date is not None else None,
                    "video_rating": video_rating,
                    "video_duration": video_duration,
                    "video_view_count": video_view_count,
                    "restriction": restriction.text if restriction is not None else None,
                    "video_restricted": (
                        True if restriction is not None and restriction.attrib.get("relationship") == "deny" else False
                    )
                })
        except Exception as e:
            error_count += 1
            logger.warning(f"解析單筆資料失敗: {e}")
            continue

    logger.info(f"成功解析 {len(data)} 筆資料，{error_count} 筆失敗")

    if not data:
        logger.error("沒有取得任何資料")
        sys.exit(1)

    df = pd.DataFrame(data)
    logger.info(f"DataFrame 初始化完成，共 {len(df)} 筆資料")

    # 1. 優先處理編碼還原 (例如 &#039; -> ')
    df['video_title'] = df['video_title'].fillna('')  # 填充空值
    df['video_title'] = df['video_title'].apply(html.unescape)
    df['video_publication_date'] = pd.to_datetime(df['video_publication_date'], errors='coerce')

    # 2. 標記特徵 (不先刪除標題內容，確保提取精準)
    df['R18'] = df['video_title'].str.contains(r'\[年齡限制版\]', regex=True)

    # 3. 提取影片類型與語系 (利用 Regex 一次性匹配多個關鍵字)
    df['clean_title'] = df['video_title'].str.replace(r'\[年齡限制版\]', '', regex=True)
    df['clean_title'] = df['clean_title'].str.replace("[中文特別篇]", '[中文配音][特別篇]', regex=False).str.strip()
    type_pattern = r'\[(電影|特別篇)\]'
    lang_pattern = r'\[(中文配音|台語配音|粵語配音)\]'
    df['video_type'] = df['clean_title'].str.extract(type_pattern)
    df['video_language'] = df['clean_title'].str.extract(lang_pattern)

    # 4. 清理標題 (移除所有已提取的標籤)
    # 這樣 Fate/stay night [Unlimited Blade Works] 內部的括號會被保留
    clean_pattern = r'(\s?\[(年齡限制版|電影|特別篇|中文配音|台語配音|粵語配音)\])+$'
    df['clean_title'] = df['clean_title'].str.replace(clean_pattern, '', regex=True).str.strip()

    # 5. 提取集數標籤 (精準鎖定末尾的中括號)
    # 使用 [^\]]+ 代表匹配括號內非 ] 的所有字元，$ 代表字串結尾
    df['episode_label'] = df['clean_title'].str.extract(r'\[([^\]]+)\]$')

    # 6. 生成 episode_sort (延用你寫得很好的 to_sort_value)
    def to_sort_value(label):
        if pd.isna(label): return None
        # 處理 1A, 26B -> 1.1, 26.2
        match = re.match(r'(\d+)([a-zA-Z])', str(label))
        if match:
            return float(match.group(1)) + (ord(match.group(2).upper()) - 64) * 0.1
        # 處理純數字或 6.5
        try:
            return float(label)
        except:
            return None

    df['episode_sort'] = df['episode_label'].apply(to_sort_value)
    df['clean_title'] = df['clean_title'].str.replace(r'\[([^\]]+)\]$', '', regex=True).str.strip()
    logger.info(f"資料處理完成")

    # 建立資料庫連線引擎
    # 格式: postgresql://使用者:密碼@主機名稱:埠號/資料庫名稱
    # 優先讀取環境變數，如果沒有就用本地連線（方便你開發測試）
    db_url = os.getenv('DATABASE_URL', 'postgresql://admin:password123@localhost:5432/anime_warehouse')

    try:
        engine = create_engine(db_url, pool_pre_ping=True)
        # 測試資料庫連線
        logger.info("測試資料庫連線...")
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.commit()
        logger.info("資料庫連線成功")
    except SQLAlchemyError as e:
        logger.error(f"資料庫連線失敗: {e}")
        sys.exit(1)

    # 使用 Upsert 將 DataFrame 寫入資料庫
    try:
        save_to_db_upsert(df, 'raw_anime_data', engine)
    except SQLAlchemyError as e:
        logger.error(f"資料寫入失敗: {e}")
        sys.exit(1)
    finally:
        engine.dispose()


if __name__ == '__main__':
    scrape_anime_data()