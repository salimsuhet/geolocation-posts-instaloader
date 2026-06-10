-- Quantidade de locations OSM resolvidas para IDs do Instagram
-- Mostra o total de POIs do OSM que têm correspondência no Instagram

SELECT COUNT(*) AS locations_resolvidas
FROM ig_locations
WHERE osm_name IS NOT NULL;
