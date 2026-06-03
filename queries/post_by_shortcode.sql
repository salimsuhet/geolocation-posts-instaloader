-- Todos os métodos de geolocalização para um post específico
-- Substitua 'SHORTCODE_AQUI' pelo shortcode do post desejado

SELECT
    method,
    lat,
    lon,
    confidence,
    available
FROM ig_post_geolocations
WHERE post_id = 'SHORTCODE_AQUI'
ORDER BY confidence DESC;
