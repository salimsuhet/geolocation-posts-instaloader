-- Progresso da varredura geo_grid: quantos pontos da grade já foram
-- escaneados para o step_km atual, quantas locations já estão no banco,
-- e quando foi o último ponto processado.

SELECT
    s.step_km,
    COUNT(*)                                    AS pontos_escaneados,
    SUM(s.venues_found)                         AS venues_encontrados_total,
    (SELECT COUNT(*) FROM ig_locations)         AS locations_no_banco,
    MIN(s.scanned_at)                           AS primeiro_ponto_em,
    MAX(s.scanned_at)                           AS ultimo_ponto_em

FROM ig_geo_grid_scanned s
GROUP BY s.step_km
ORDER BY s.step_km;
