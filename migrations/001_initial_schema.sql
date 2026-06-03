-- =============================================================
-- Infraestrutura: coleta de posts Instagram - Grande Vitória ES
-- Modelo multi-método: cada post tem uma linha por método geo
-- =============================================================

CREATE EXTENSION IF NOT EXISTS postgis;

-- -------------------------------------------------------------
-- Métodos de geolocalização (tabela de referência)
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS geo_methods (
    method       TEXT     PRIMARY KEY,
    description  TEXT     NOT NULL,
    confidence   SMALLINT NOT NULL CHECK (confidence BETWEEN 0 AND 100)
);

INSERT INTO geo_methods VALUES
    ('post_latlon',
     'Coordenada lat/lon do objeto post.location (campo direto da API)',
     95),
    ('location_centroid',
     'Centroide da IG location associada ao post',
     70),
    ('osm_match',
     'Coordenada do ponto OSM que originou o match da IG location',
     50),
    ('bbox_centroid',
     'Centro do bounding box de busca — fallback geográfico grosseiro',
     10)
ON CONFLICT DO NOTHING;

-- -------------------------------------------------------------
-- Locations do Instagram resolvidas a partir do OSM
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ig_locations (
    ig_location_id  BIGINT           PRIMARY KEY,
    name            TEXT             NOT NULL,
    -- coordenada reportada pela API do Instagram
    ig_lat          DOUBLE PRECISION,
    ig_lon          DOUBLE PRECISION,
    ig_geom         GEOMETRY(Point, 4326) GENERATED ALWAYS AS (
                        CASE WHEN ig_lat IS NOT NULL AND ig_lon IS NOT NULL
                             THEN ST_SetSRID(ST_MakePoint(ig_lon, ig_lat), 4326)
                        END
                    ) STORED,
    -- coordenada do ponto OSM que originou o match
    osm_lat         DOUBLE PRECISION,
    osm_lon         DOUBLE PRECISION,
    osm_geom        GEOMETRY(Point, 4326) GENERATED ALWAYS AS (
                        CASE WHEN osm_lat IS NOT NULL AND osm_lon IS NOT NULL
                             THEN ST_SetSRID(ST_MakePoint(osm_lon, osm_lat), 4326)
                        END
                    ) STORED,
    osm_name        TEXT,
    resolved_at     TIMESTAMPTZ      DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ig_locations_ig_geom_idx  ON ig_locations USING GIST (ig_geom);
CREATE INDEX IF NOT EXISTS ig_locations_osm_geom_idx ON ig_locations USING GIST (osm_geom);

-- -------------------------------------------------------------
-- Posts coletados (metadados apenas — sem coluna de geo aqui)
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ig_posts (
    post_id         TEXT         PRIMARY KEY,
    taken_at        TIMESTAMPTZ  NOT NULL,
    ig_location_id  BIGINT       REFERENCES ig_locations(ig_location_id),
    owner_username  TEXT,
    caption_snippet TEXT,
    collected_at    TIMESTAMPTZ  DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ig_posts_taken_at_idx   ON ig_posts (taken_at DESC);
CREATE INDEX IF NOT EXISTS ig_posts_location_idx   ON ig_posts (ig_location_id);

-- -------------------------------------------------------------
-- Geolocalizações — uma linha por (post, método)
-- NULL em lat/lon significa que o método não pôde produzir coord
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ig_post_geolocations (
    post_id     TEXT     NOT NULL REFERENCES ig_posts(post_id) ON DELETE CASCADE,
    method      TEXT     NOT NULL REFERENCES geo_methods(method),
    lat         DOUBLE PRECISION,
    lon         DOUBLE PRECISION,
    geom        GEOMETRY(Point, 4326) GENERATED ALWAYS AS (
                    CASE WHEN lat IS NOT NULL AND lon IS NOT NULL
                         THEN ST_SetSRID(ST_MakePoint(lon, lat), 4326)
                    END
                ) STORED,
    confidence  SMALLINT NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    available   BOOLEAN  GENERATED ALWAYS AS (lat IS NOT NULL AND lon IS NOT NULL) STORED,

    PRIMARY KEY (post_id, method)
);

CREATE INDEX IF NOT EXISTS ig_post_geo_geom_idx      ON ig_post_geolocations USING GIST (geom);
CREATE INDEX IF NOT EXISTS ig_post_geo_method_idx    ON ig_post_geolocations (method);
CREATE INDEX IF NOT EXISTS ig_post_geo_available_idx ON ig_post_geolocations (available);

-- -------------------------------------------------------------
-- View analítica: posts no formato wide (um método por coluna)
-- Facilita calcular distâncias entre métodos diretamente no SQL
-- -------------------------------------------------------------
CREATE OR REPLACE VIEW vw_posts_methods_wide AS
SELECT
    p.post_id,
    p.taken_at,
    p.owner_username,
    l.name                      AS location_name,

    -- post_latlon
    pl.lat                      AS pl_lat,
    pl.lon                      AS pl_lon,
    pl.available                AS pl_available,

    -- location_centroid
    lc.lat                      AS lc_lat,
    lc.lon                      AS lc_lon,
    lc.available                AS lc_available,

    -- osm_match
    om.lat                      AS om_lat,
    om.lon                      AS om_lon,
    om.available                AS om_available,

    -- bbox_centroid (sempre disponível)
    bc.lat                      AS bc_lat,
    bc.lon                      AS bc_lon,

    -- distância entre os métodos mais precisos disponíveis (metros)
    CASE WHEN pl.geom IS NOT NULL AND lc.geom IS NOT NULL
         THEN ROUND(ST_Distance(pl.geom::geography, lc.geom::geography)::NUMERIC, 1)
    END                         AS dist_pl_lc_m,

    CASE WHEN pl.geom IS NOT NULL AND om.geom IS NOT NULL
         THEN ROUND(ST_Distance(pl.geom::geography, om.geom::geography)::NUMERIC, 1)
    END                         AS dist_pl_om_m,

    CASE WHEN lc.geom IS NOT NULL AND om.geom IS NOT NULL
         THEN ROUND(ST_Distance(lc.geom::geography, om.geom::geography)::NUMERIC, 1)
    END                         AS dist_lc_om_m

FROM ig_posts p
LEFT JOIN ig_locations          l   USING (ig_location_id)
LEFT JOIN ig_post_geolocations  pl  ON pl.post_id = p.post_id AND pl.method = 'post_latlon'
LEFT JOIN ig_post_geolocations  lc  ON lc.post_id = p.post_id AND lc.method = 'location_centroid'
LEFT JOIN ig_post_geolocations  om  ON om.post_id = p.post_id AND om.method = 'osm_match'
LEFT JOIN ig_post_geolocations  bc  ON bc.post_id = p.post_id AND bc.method = 'bbox_centroid';

-- -------------------------------------------------------------
-- View de cobertura: quantos posts têm cada método disponível
-- -------------------------------------------------------------
CREATE OR REPLACE VIEW vw_method_coverage AS
SELECT
    m.method,
    m.confidence,
    m.description,
    COUNT(g.post_id)                                        AS total_registros,
    COUNT(g.post_id) FILTER (WHERE g.available)            AS com_coordenada,
    COUNT(g.post_id) FILTER (WHERE NOT g.available)        AS sem_coordenada,
    ROUND(
        100.0 * COUNT(g.post_id) FILTER (WHERE g.available)
              / NULLIF(COUNT(g.post_id), 0), 1
    )                                                       AS pct_disponivel
FROM geo_methods m
LEFT JOIN ig_post_geolocations g USING (method)
GROUP BY m.method, m.confidence, m.description
ORDER BY m.confidence DESC;

-- -------------------------------------------------------------
-- View de correlação por location: desvio médio entre métodos
-- Útil para identificar locations onde os métodos divergem mais
-- -------------------------------------------------------------
CREATE OR REPLACE VIEW vw_location_method_divergence AS
SELECT
    l.ig_location_id,
    l.name                              AS location_name,
    COUNT(DISTINCT p.post_id)           AS total_posts,
    ROUND(AVG(w.dist_pl_lc_m)::NUMERIC, 1) AS avg_dist_pl_lc_m,
    ROUND(AVG(w.dist_pl_om_m)::NUMERIC, 1) AS avg_dist_pl_om_m,
    ROUND(AVG(w.dist_lc_om_m)::NUMERIC, 1) AS avg_dist_lc_om_m
FROM ig_locations l
JOIN ig_posts p USING (ig_location_id)
JOIN vw_posts_methods_wide w USING (post_id)
GROUP BY l.ig_location_id, l.name
HAVING COUNT(DISTINCT p.post_id) > 0
ORDER BY avg_dist_pl_lc_m DESC NULLS LAST;

-- -------------------------------------------------------------
-- Fonte da coleta (adicionado para suporte a hashtags)
-- -------------------------------------------------------------
ALTER TABLE ig_posts
    ADD COLUMN IF NOT EXISTS source      TEXT DEFAULT 'location'
                                         CHECK (source IN ('location', 'hashtag')),
    ADD COLUMN IF NOT EXISTS source_value TEXT;  -- location_id ou hashtag usada

COMMENT ON COLUMN ig_posts.source       IS 'location = coletado via location ID; hashtag = coletado via hashtag';
COMMENT ON COLUMN ig_posts.source_value IS 'Valor da fonte: location name ou #hashtag';
