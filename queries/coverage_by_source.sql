-- Cobertura por fonte de coleta (location vs hashtag)
-- Mostra quantos posts cada fonte trouxe e a disponibilidade de cada método geo

SELECT
    p.source,
    COUNT(DISTINCT p.post_id)                                       AS total_posts,
    COUNT(DISTINCT p.post_id) FILTER (WHERE g.method = 'post_latlon'
                                        AND g.available)            AS com_post_latlon,
    COUNT(DISTINCT p.post_id) FILTER (WHERE g.method = 'location_centroid'
                                        AND g.available)            AS com_location_centroid,
    COUNT(DISTINCT p.post_id) FILTER (WHERE g.method = 'osm_match'
                                        AND g.available)            AS com_osm_match
FROM ig_posts p
LEFT JOIN ig_post_geolocations g USING (post_id)
GROUP BY p.source
ORDER BY p.source;
