-- =============================================================
-- Cache de progresso da coleta de posts por location: marca quando os
-- posts de uma location já foram coletados, para que uma reexecução
-- (após crash/interrupção) retome dali em vez de revisitar tudo de novo.
-- =============================================================

ALTER TABLE ig_locations
    ADD COLUMN IF NOT EXISTS posts_collected_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ig_locations_posts_collected_idx ON ig_locations (posts_collected_at);

COMMENT ON COLUMN ig_locations.posts_collected_at IS
    'Quando os posts dessa location foram coletados com sucesso. NULL = ainda pendente.';
