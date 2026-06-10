-- Lista completa de locations OSM resolvidas para IDs do Instagram
-- Mostra nome OSM, nome no Instagram, coordenadas e distância entre os dois pontos

SELECT
    l.ig_location_id,
    l.osm_name                                          AS nome_osm,
    l.name                                              AS nome_instagram,
    ROUND(l.osm_lat::NUMERIC, 6)                        AS osm_lat,
    ROUND(l.osm_lon::NUMERIC, 6)                        AS osm_lon,
    ROUND(l.ig_lat::NUMERIC, 6)                         AS ig_lat,
    ROUND(l.ig_lon::NUMERIC, 6)                         AS ig_lon,
    CASE
        WHEN l.osm_geom IS NOT NULL AND l.ig_geom IS NOT NULL
        THEN ROUND(ST_Distance(l.osm_geom::geography, l.ig_geom::geography)::NUMERIC, 1)
    END                                                 AS distancia_osm_ig_m,
    l.resolved_at                                       AS resolvida_em,
    COUNT(p.post_id)                                    AS total_posts

FROM ig_locations l
LEFT JOIN ig_posts p USING (ig_location_id)
WHERE l.osm_name IS NOT NULL
GROUP BY
    l.ig_location_id, l.osm_name, l.name,
    l.osm_lat, l.osm_lon, l.ig_lat, l.ig_lon,
    l.osm_geom, l.ig_geom, l.resolved_at

ORDER BY total_posts DESC, l.osm_name;
