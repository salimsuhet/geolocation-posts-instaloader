-- Locations onde os métodos mais divergem (média de distância em metros)
-- Ordena pelas locations com maior discrepância média entre post_latlon e location_centroid

SELECT * FROM vw_location_method_divergence
LIMIT 20;
