# 1. 使用官方 Python 輕量版作為底層
FROM python:3.11-slim

# 2. 設定時區為台灣 (UTC+8)
RUN apt-get update && apt-get install -y tzdata && \
    ln -sf /usr/share/zoneinfo/Asia/Taipei /etc/localtime && \
    echo "Asia/Taipei" > /etc/timezone && \
    rm -rf /var/lib/apt/lists/*

# 3. 設定容器內的工作目錄
WORKDIR /app

# 4. 先複製套件清單並安裝 (這樣可以利用快取，加快以後打包的速度)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 創建非 root 用戶提高安全性
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# 6. 複製所有爬蟲程式碼到容器裡
COPY --chown=appuser:appuser animeData.py .
COPY --chown=appuser:appuser anime_metadata_scraper.py .
COPY --chown=appuser:appuser orchestrator.py .

# 7. 新增標籤（可選，便於管理）
LABEL maintainer="your-email@example.com" \
      version="1.0" \
      description="AniBrowser Crawler - 爬取動畫瘋影片資料 & 元數據" \
      orchestrator="true"

# 8. 告訴 Docker 啟動時執行協調器
CMD ["python", "orchestrator.py"]