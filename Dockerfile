# 1. 使用官方 Python 輕量版作為底層
FROM python:3.11-slim

# 2. 設定容器內的工作目錄
WORKDIR /app

# 3. 先複製套件清單並安裝 (這樣可以利用快取，加快以後打包的速度)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. 創建非 root 用戶提高安全性
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# 5. 複製你的爬蟲程式碼到容器裡
COPY --chown=appuser:appuser animeData.py .

# 6. 新增標籤（可選，便於管理）
LABEL maintainer="your-email@example.com" \
      version="1.0" \
      description="AniBrowser Crawler - 爬取動畫瘋影片資料"

# 7. 告訴 Docker 啟動時執行哪一個檔案
CMD ["python", "animeData.py"]