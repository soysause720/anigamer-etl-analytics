CREATE OR REPLACE VIEW public.v_clean_tv_animelist AS
WITH EpisodeMetrics AS (
    SELECT 
        *,
        FIRST_VALUE(url) OVER (PARTITION BY title ORDER BY episode ASC) AS first_url,
        FIRST_VALUE(view_count) OVER (PARTITION BY title ORDER BY episode ASC) AS v1
    FROM public.v_clean_tv_episodes
)
SELECT 
    title,
    COUNT(*) AS episodes,
    MIN(rating) AS rating,
    ROUND(AVG(view_count)) AS mean_view_count,
    SUM(view_count) AS sum_view_count,
    CASE 
        WHEN COUNT(*) <= 1 THEN 'N/A'
        ELSE 
            TO_CHAR(
                (SUM(
                    CASE 
                        WHEN episode > 1 AND view_count < v1 THEN (v1 - view_count)::numeric / v1 
                        ELSE 0 
                    END
                ) / (COUNT(*) - 1)) * 100, 
                '990.9'
            ) || '%'
    END AS churn_rate,
    CASE MIN(CASE changefreq 
        WHEN 'hourly' THEN 1 
        WHEN 'daily' THEN 2 
        WHEN 'weekly' THEN 3 
    END)
        WHEN 1 THEN 'hourly'
        WHEN 2 THEN 'daily'
        WHEN 3 THEN 'weekly'
    END AS frequency,
    CASE 
        WHEN CAST(MIN(pub_date) AS DATE) = CAST(MAX(pub_date) AS DATE) THEN FALSE
        ELSE TRUE
    END AS aired_weekly,
    CASE
        WHEN COUNT(*) <= 6 THEN '短篇動畫'
        WHEN COUNT(*) <= 15 THEN '季番'
        WHEN COUNT(*) <= 30 THEN '半年番'
        ELSE '長篇動畫'
    END AS type,
    CASE
        WHEN CAST(MIN(pub_date) AS DATE) = CAST(MAX(pub_date) AS DATE) THEN NULL
        WHEN (episodemetrics.title = 'Fate/strange Fake') THEN 2026
        ELSE EXTRACT(YEAR FROM (CAST(MIN(pub_date) AS DATE) + INTERVAL '14 days')) 
    END AS year,
    CASE 
        WHEN CAST(MIN(pub_date) AS DATE) = CAST(MAX(pub_date) AS DATE) THEN NULL
        WHEN EXTRACT(MONTH FROM (CAST(MIN(pub_date) AS DATE) + INTERVAL '14 days')) BETWEEN 1 AND 3 THEN '冬番'
        WHEN EXTRACT(MONTH FROM (CAST(MIN(pub_date) AS DATE) + INTERVAL '14 days')) BETWEEN 4 AND 6 THEN '春番'
        WHEN EXTRACT(MONTH FROM (CAST(MIN(pub_date) AS DATE) + INTERVAL '14 days')) BETWEEN 7 AND 9 THEN '夏番'
        WHEN EXTRACT(MONTH FROM (CAST(MIN(pub_date) AS DATE) + INTERVAL '14 days')) BETWEEN 10 AND 12 THEN '秋番'
    END AS season,
    MIN(pub_date) AS first_pub_date,
    MAX(pub_date) AS last_pub_date,
    BOOL_OR(r18) AS r18,
    MIN(first_url) AS url
FROM EpisodeMetrics
GROUP BY title
ORDER BY mean_view_count DESC;