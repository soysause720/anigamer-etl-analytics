CREATE TABLE IF NOT EXISTS public.anime_metadata (
    url TEXT PRIMARY KEY,           -- 這是主鍵，對應腳本的 on_conflict_do_nothing
    title TEXT,
    agent TEXT,
    studio TEXT,
    tags JSONB,                     -- 儲存 ["標籤1", "標籤2"] 格式
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
