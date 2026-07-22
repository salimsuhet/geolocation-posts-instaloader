-- Lista completa de locations descobertas pela varredura geo_grid.
-- Inclui locations sem match OSM (osm_name IS NULL), já que o geo_grid
-- descobre tudo que está registrado na área, independente de nome.

SELECT
    l.ig_location_id,
    l.name,
    ROUND(l.ig_lat::NUMERIC, 6) AS lat,
    ROUND(l.ig_lon::NUMERIC, 6) AS lon,
    l.osm_name,
    l.resolved_at,
    COUNT(p.post_id)            AS total_posts

FROM ig_locations l
LEFT JOIN ig_posts p USING (ig_location_id)
GROUP BY l.ig_location_id, l.name, l.ig_lat, l.ig_lon, l.osm_name, l.resolved_at
ORDER BY l.resolved_at DESC;
