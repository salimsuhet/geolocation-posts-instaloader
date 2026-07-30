-- Progresso da coleta de posts por location: quantas locations já foram
-- processadas (posts_collected_at preenchido), quantas faltam, total de
-- posts coletados até agora, e quando foi a última location processada.

SELECT
    COUNT(*)                                                AS total_locations,
    COUNT(*) FILTER (WHERE posts_collected_at IS NOT NULL)  AS locations_coletadas,
    COUNT(*) FILTER (WHERE posts_collected_at IS NULL)      AS locations_pendentes,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE posts_collected_at IS NOT NULL)
              / NULLIF(COUNT(*), 0), 1
    )                                                        AS pct_concluido,
    (SELECT COUNT(*) FROM ig_posts)                         AS total_posts_coletados,
    MAX(posts_collected_at)                                 AS ultima_location_processada_em

FROM ig_locations;
