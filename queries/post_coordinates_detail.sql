-- Coordenadas e detalhes completos de cada post
-- Exibe os 4 métodos de geolocalização lado a lado com distâncias entre eles
-- Ordenado do post mais recente para o mais antigo

SELECT
    p.post_id,
    p.taken_at                              AS data_post,
    p.owner_username,
    p.source,
    p.source_value,
    p.caption_snippet,
    l.name                                  AS location_name,

    -- post_latlon (confiança 95) — coordenada direta da API
    pl.lat                                  AS pl_lat,
    pl.lon                                  AS pl_lon,
    pl.available                            AS pl_disponivel,

    -- location_centroid (confiança 70) — centroide da IG location
    lc.lat                                  AS lc_lat,
    lc.lon                                  AS lc_lon,
    lc.available                            AS lc_disponivel,

    -- osm_match (confiança 50) — ponto OSM que originou o match
    om.lat                                  AS om_lat,
    om.lon                                  AS om_lon,
    om.available                            AS om_disponivel,

    -- bbox_centroid (confiança 10) — centro do bounding box, sempre presente
    bc.lat                                  AS bc_lat,
    bc.lon                                  AS bc_lon,

    -- distâncias entre métodos (metros)
    CASE WHEN pl.geom IS NOT NULL AND lc.geom IS NOT NULL
         THEN ROUND(ST_Distance(pl.geom::geography, lc.geom::geography)::NUMERIC, 1)
    END                                     AS dist_pl_lc_m,

    CASE WHEN pl.geom IS NOT NULL AND om.geom IS NOT NULL
         THEN ROUND(ST_Distance(pl.geom::geography, om.geom::geography)::NUMERIC, 1)
    END                                     AS dist_pl_om_m,

    CASE WHEN lc.geom IS NOT NULL AND om.geom IS NOT NULL
         THEN ROUND(ST_Distance(lc.geom::geography, om.geom::geography)::NUMERIC, 1)
    END                                     AS dist_lc_om_m,

    -- número de métodos com coordenada disponível
    (COALESCE(pl.available::int, 0)
   + COALESCE(lc.available::int, 0)
   + COALESCE(om.available::int, 0)
   + 1)                                     AS metodos_disponiveis

FROM ig_posts p
LEFT JOIN ig_locations          l   USING (ig_location_id)
LEFT JOIN ig_post_geolocations  pl  ON pl.post_id = p.post_id AND pl.method = 'post_latlon'
LEFT JOIN ig_post_geolocations  lc  ON lc.post_id = p.post_id AND lc.method = 'location_centroid'
LEFT JOIN ig_post_geolocations  om  ON om.post_id = p.post_id AND om.method = 'osm_match'
LEFT JOIN ig_post_geolocations  bc  ON bc.post_id = p.post_id AND bc.method = 'bbox_centroid'

ORDER BY p.taken_at DESC;
