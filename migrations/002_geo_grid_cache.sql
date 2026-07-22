-- =============================================================
-- Cache de varredura do geo_grid: registra pontos da grade já
-- consultados no location_search para evitar refazer a varredura
-- inteira a cada execução.
-- =============================================================

CREATE TABLE IF NOT EXISTS ig_geo_grid_scanned (
    lat          DOUBLE PRECISION NOT NULL,
    lon          DOUBLE PRECISION NOT NULL,
    step_km      DOUBLE PRECISION NOT NULL,
    venues_found SMALLINT         NOT NULL DEFAULT 0,
    scanned_at   TIMESTAMPTZ      NOT NULL DEFAULT now(),

    PRIMARY KEY (lat, lon, step_km)
);

CREATE INDEX IF NOT EXISTS ig_geo_grid_scanned_step_idx ON ig_geo_grid_scanned (step_km);

COMMENT ON TABLE ig_geo_grid_scanned IS
    'Cache de pontos da grade geo_grid já consultados no location_search. '
    'step_km faz parte da chave para não bloquear uma revarredura mais densa.';
