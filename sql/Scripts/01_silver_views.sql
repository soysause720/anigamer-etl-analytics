CREATE OR REPLACE VIEW public.v_clean_tv_episodes AS
WITH VersionRepresentatives AS (
    SELECT 
        clean_title AS title,
        floor(episode_sort) AS main_episode,
        "R18" AS is_r18, 
        MAX(video_view_count) AS version_max_view
    FROM public.raw_anime_data
    WHERE (video_type = 'NaN' or video_type is null) 
      AND (video_language = 'NaN' or video_language is null)
    GROUP BY clean_title, floor(episode_sort), "R18"
),
-- 2. 第二層：將「一般版最高」與「R18版最高」進行加總
TotalMetrics AS (
    SELECT 
        title,
        main_episode,
        SUM(version_max_view) AS final_view_count,
        bool_or(is_r18) AS R18
    FROM VersionRepresentatives
    GROUP BY title, main_episode
),
-- 3. 第三層：取得網址（優先抓「一般版」且「整數集」的 URL）
CanonicalInfo AS (
    SELECT DISTINCT ON (clean_title, floor(episode_sort))
        clean_title AS title,
        floor(episode_sort) AS main_episode,
        loc AS url,
        changefreq,
        video_publication_date AS pub_date,
        video_rating AS rating
    FROM public.raw_anime_data
    WHERE (video_type = 'NaN' or video_type is null) 
      AND (video_language = 'NaN' or video_language is null)
    ORDER BY clean_title, floor(episode_sort), "R18" ASC, episode_sort ASC
)
-- 最終合併結果 (執行時請務必連同上面的 WITH 一起選取)
SELECT 
    t.title,
    t.main_episode AS episode,
    c.rating,
    ROUND(t.final_view_count) AS view_count,
    t.R18,
    c.changefreq,
    c.pub_date,
    c.url
FROM TotalMetrics t
JOIN CanonicalInfo c ON t.title = c.title AND t.main_episode = c.main_episode
ORDER BY t.title, t.main_episode ASC;