-- Lista de hashtags geradas automaticamente a partir dos POIs OSM
-- Mostra quantos posts foram coletados por cada hashtag automática

SELECT
    p.source_value                          AS hashtag,
    COUNT(p.post_id)                        AS total_posts,
    MIN(p.taken_at)                         AS post_mais_antigo,
    MAX(p.taken_at)                         AS post_mais_recente,
    COUNT(DISTINCT p.owner_username)        AS usuarios_unicos

FROM ig_posts p
WHERE p.source = 'hashtag'
  AND p.source_value IS NOT NULL

GROUP BY p.source_value
ORDER BY total_posts DESC, p.source_value;
