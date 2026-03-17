import subprocess
import sys
import os
import logging
from datetime import datetime, date
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from time import sleep

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_db_connection(db_url: str) -> bool:
    """檢查資料庫連線"""
    try:
        engine = create_engine(db_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.commit()
        logger.info("✓ 資料庫連線成功")
        engine.dispose()
        return True
    except SQLAlchemyError as e:
        logger.error(f"✗ 資料庫連線失敗: {e}")
        return False


def check_today_updates(db_url: str) -> dict:
    """
    檢查 raw_anime_data 表是否有數據。
    
    Returns:
        {
            'has_updates': bool,
            'update_count': int,
            'latest_timestamp': str
        }
    """
    try:
        engine = create_engine(db_url, pool_pre_ping=True)
        
        # 檢查表中是否有任何數據
        query = """
        SELECT COUNT(*) as count
        FROM public.raw_anime_data
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(query))
            row = result.fetchone()
        
        engine.dispose()
        
        count = row[0] if row else 0
        
        return {
            'has_updates': count > 0,
            'update_count': count,
            'latest_timestamp': datetime.now().isoformat()
        }
    
    except SQLAlchemyError as e:
        logger.error(f"✗ 查詢資料庫失敗: {e}")
        return {
            'has_updates': False,
            'update_count': 0,
            'latest_timestamp': None
        }


def run_anime_scraper(db_url: str) -> int:
    """執行 animeData.py，返回程式的 exit code"""
    logger.info("=" * 60)
    logger.info("【第一階段】開始執行 animeData.py（爬取 Sitemap）")
    logger.info("=" * 60)
    
    try:
        result = subprocess.run(
            [sys.executable, 'animeData.py'],
            env={**os.environ, 'DATABASE_URL': db_url},
            check=False,
            capture_output=False
        )
        
        if result.returncode == 0:
            logger.info("✓ animeData.py 執行成功")
            return 0
        else:
            logger.error(f"✗ animeData.py 執行失敗，返回碼: {result.returncode}")
            return result.returncode
    
    except Exception as e:
        logger.error(f"✗ 執行 animeData.py 時發生錯誤: {e}")
        return 1


def run_metadata_scraper(db_url: str) -> int:
    """執行 anime_metadata_scraper.py，返回程式的 exit code"""
    logger.info("=" * 60)
    logger.info("【第二階段】開始執行 anime_metadata_scraper.py（爬取元數據）")
    logger.info("=" * 60)
    
    try:
        result = subprocess.run(
            [sys.executable, 'anime_metadata_scraper.py', '--db-url', db_url],
            check=False,
            capture_output=False
        )
        
        if result.returncode == 0:
            logger.info("✓ anime_metadata_scraper.py 執行成功")
            return 0
        else:
            logger.error(f"✗ anime_metadata_scraper.py 執行失敗，返回碼: {result.returncode}")
            return result.returncode
    
    except Exception as e:
        logger.error(f"✗ 執行 anime_metadata_scraper.py 時發生錯誤: {e}")
        return 1


def main():
    """主協調流程"""
    
    logger.info("=" * 60)
    logger.info("🎬 動畫爬蟲協調器啟動")
    logger.info("=" * 60)
    
    # 讀取環境變數
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        logger.error("✗ 環境變數 DATABASE_URL 未設定，程式終止")
        sys.exit(1)
    
    crawler_delay = int(os.getenv('CRAWLER_DELAY', 30))
    stop_on_first_failure = os.getenv('STOP_ON_FIRST_FAILURE', 'true').lower() == 'true'
    
    logger.info(f"資料庫: {db_url.split('@')[-1] if '@' in db_url else 'Unknown'}")
    logger.info(f"爬蟲延遲: {crawler_delay} 秒")
    logger.info(f"失敗即中止: {stop_on_first_failure}")
    
    # 檢查資料庫連線
    if not check_db_connection(db_url):
        logger.error("✗ 無法連接資料庫，程式終止")
        sys.exit(1)
    
    # 第一階段：執行 animeData.py
    logger.info("")
    scraper_exit_code = run_anime_scraper(db_url)
    
    if scraper_exit_code != 0:
        if stop_on_first_failure:
            logger.error("✗ animeData.py 執行失敗，程式中止")
            sys.exit(1)
        else:
            logger.warning("⚠ animeData.py 執行失敗，但繼續執行後續流程")
    
    # 智能延遲與檢查：檢查今天是否有新數據
    logger.info("")
    logger.info("檢查今天的數據更新情況...")
    update_info = check_today_updates(db_url)
    
    if update_info['has_updates']:
        logger.info(f"✓ 今天新增 {update_info['update_count']} 筆數據")
        logger.info(f"  最新時戳: {update_info['latest_timestamp']}")
        
        # 第二階段：等待後執行 anime_metadata_scraper.py
        logger.info("")
        logger.info(f"等待 {crawler_delay} 秒，讓資料庫穩定...")
        for i in range(crawler_delay, 0, -1):
            if i % 10 == 0 or i <= 3:
                logger.debug(f"  倒數: {i} 秒")
            sleep(1)
        
        logger.info("")
        metadata_exit_code = run_metadata_scraper(db_url)
        
        if metadata_exit_code != 0:
            if stop_on_first_failure:
                logger.error("✗ anime_metadata_scraper.py 執行失敗，程式中止")
                sys.exit(1)
            else:
                logger.warning("⚠ anime_metadata_scraper.py 執行失敗")
    else:
        logger.warning(f"⚠ 今天沒有新數據更新，跳過 anime_metadata_scraper.py")
        logger.info("  原因: raw_anime_data 表中今天的記錄數為 0")
    
    # 最終狀態
    logger.info("")
    logger.info("=" * 60)
    logger.info("✅ 所有爬蟲流程完成")
    logger.info("=" * 60)
    sys.exit(0)


if __name__ == '__main__':
    main()
