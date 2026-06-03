-- Posts com maior divergência entre métodos (distância em metros)
-- Útil para identificar posts onde os métodos geo discordam

SELECT
    post_id,
    location_name,
    dist_pl_lc_m,   -- post_latlon vs location_centroid
    dist_pl_om_m,   -- post_latlon vs osm_match
    dist_lc_om_m    -- location_centroid vs osm_match
FROM vw_posts_methods_wide
WHERE dist_pl_lc_m IS NOT NULL
ORDER BY dist_pl_lc_m DESC
LIMIT 20;
