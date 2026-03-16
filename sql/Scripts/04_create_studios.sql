-- 1. 正式公司名單
CREATE TABLE IF NOT EXISTS public.studios (
    id SERIAL PRIMARY KEY,
    official_name TEXT UNIQUE
);
-- 2. 別名對應表
CREATE TABLE IF NOT EXISTS public.studio_aliases (
    alias_name TEXT PRIMARY KEY,
    studio_id INTEGER REFERENCES public.studios(id)
);
-- 3. 作品與公司的中繼表 (多對多)
CREATE TABLE IF NOT EXISTS public.anime_studio_map (
    anime_url TEXT REFERENCES public.anime_metadata(url),
    studio_id INTEGER REFERENCES public.studios(id),
    PRIMARY KEY (anime_url, studio_id)
);