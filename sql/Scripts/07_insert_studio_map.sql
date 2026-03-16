-- 這段語法會將原始字串拆開，並嘗試對應已有的別名
INSERT INTO public.anime_studio_map (anime_url, studio_id)
SELECT 
    m.url,
    a.studio_id
FROM (
    -- 使用正規表達式拆分 studio 欄位
    SELECT url, regexp_split_to_table(studio, '[、×]') as raw_studio_name
    FROM public.anime_metadata
    WHERE studio IS NOT NULL
) m
JOIN public.studio_aliases a ON TRIM(m.raw_studio_name) = a.alias_name
ON CONFLICT DO NOTHING;