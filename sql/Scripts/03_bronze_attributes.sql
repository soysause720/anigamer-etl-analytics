CREATE TABLE public.anime_attributes (
    title TEXT PRIMARY KEY,
    url TEXT,
    agent TEXT,
    studio TEXT,
    tags JSONB,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);