CREATE OR REPLACE VIEW anime_warehouse.public.v_clean_tv_episodes AS
WITH versionrepresentatives AS (
         SELECT raw_anime_data.clean_title AS title,
            floor(raw_anime_data.episode_sort) AS main_episode,
            raw_anime_data."R18" AS is_r18,
            max(raw_anime_data.video_view_count) AS version_max_view
           -- 修正點 1: 加上 public. 前綴
           FROM public.raw_anime_data AS raw_anime_data
          WHERE (((raw_anime_data.video_type = 'NaN'::text) OR (raw_anime_data.video_type IS NULL)) 
            AND ((raw_anime_data.video_language = 'NaN'::text) OR (raw_anime_data.video_language IS NULL)))
            -- 修正點 2: 使用 MOD 並轉型 numeric 解決 % 錯誤
            AND (MOD(raw_anime_data.episode_sort::numeric, 1) != 0.5) 
          GROUP BY raw_anime_data.clean_title, (floor(raw_anime_data.episode_sort)), raw_anime_data."R18"
        ), totalmetrics AS (
         SELECT versionrepresentatives.title,
            versionrepresentatives.main_episode,
            sum(versionrepresentatives.version_max_view) AS final_view_count,
            bool_or(versionrepresentatives.is_r18) AS r18
           FROM versionrepresentatives
          GROUP BY versionrepresentatives.title, versionrepresentatives.main_episode
        ), canonicalinfo AS (
         SELECT DISTINCT ON (raw_anime_data.clean_title, (floor(raw_anime_data.episode_sort))) raw_anime_data.clean_title AS title,
            floor(raw_anime_data.episode_sort) AS main_episode,
            raw_anime_data.loc AS url,
            raw_anime_data.changefreq,
            raw_anime_data.video_publication_date AS pub_date,
            raw_anime_data.video_rating AS rating
           -- 修正點 3: 加上 public. 前綴
           FROM public.raw_anime_data AS raw_anime_data
          WHERE (((raw_anime_data.video_type = 'NaN'::text) OR (raw_anime_data.video_type IS NULL)) 
            AND ((raw_anime_data.video_language = 'NaN'::text) OR (raw_anime_data.video_language IS NULL)))
            -- 修正點 4: 使用 MOD
            AND (MOD(raw_anime_data.episode_sort::numeric, 1) != 0.5)
          ORDER BY raw_anime_data.clean_title, (floor(raw_anime_data.episode_sort)), raw_anime_data."R18", raw_anime_data.episode_sort
        )
 SELECT t.title,
    t.main_episode AS episode,
    c.rating,
    round(t.final_view_count) AS view_count,
    t.r18,
    c.changefreq,
    c.pub_date,
    c.url
   FROM (totalmetrics t
     JOIN canonicalinfo c ON (((t.title = c.title) AND (t.main_episode = c.main_episode))))
  ORDER BY t.title, t.main_episode;