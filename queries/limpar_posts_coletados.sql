-- ATENÇÃO: operação destrutiva.
-- Remove todos os posts e geolocalizações coletados, e reseta o cache de
-- progresso da coleta (ig_locations.posts_collected_at) para NULL — assim
-- a próxima coleta (make collect) revisita todas as locations do zero.
-- As locations em si (ig_locations) e o cache da varredura geo_grid
-- (ig_geo_grid_scanned) NÃO são apagados.

BEGIN;

DELETE FROM ig_posts;
-- ig_post_geolocations é removido junto, em cascata (ON DELETE CASCADE)

UPDATE ig_locations SET posts_collected_at = NULL;

COMMIT;

SELECT
    (SELECT COUNT(*) FROM ig_posts)                                     AS posts_restantes,
    (SELECT COUNT(*) FROM ig_post_geolocations)                         AS geolocalizacoes_restantes,
    (SELECT COUNT(*) FROM ig_locations WHERE posts_collected_at IS NULL) AS locations_pendentes;
