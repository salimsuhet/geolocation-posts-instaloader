#!/usr/bin/env bash
# run-export.sh
# Exporta o resultado de uma query da pasta queries/ para um arquivo .csv local
# Uso: ./run-export.sh geo_grid_locations_lista
#      OUT=coverage.csv ./run-export.sh method_coverage
#      CONTAINER=meu_db ./run-export.sh geo_grid_locations_lista

set -euo pipefail

QUERY="${1:-}"
CONTAINER="${CONTAINER:-gv_instagram_db}"
DATABASE="${DATABASE:-instagram}"
DB_USER="${DB_USER:-postgres}"
QUERIES_DIR="$(dirname "$0")/queries"

if [[ -z "$QUERY" ]]; then
    echo "Uso: $0 <nome_da_query>" >&2
    echo "Exemplo: $0 geo_grid_locations_lista" >&2
    exit 1
fi

FILE="$QUERIES_DIR/$QUERY.sql"
if [[ ! -f "$FILE" ]]; then
    echo "Erro: query '$QUERY' não encontrada em $QUERIES_DIR" >&2
    exit 1
fi

OUT="${OUT:-$QUERY.csv}"

# Envolve a query original em COPY ... TO STDOUT — remove o ; final se houver
INNER_SQL="$(sed -e '$ s/;[[:space:]]*$//' "$FILE")"
COPY_SQL="COPY (${INNER_SQL}) TO STDOUT WITH CSV HEADER"

docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DATABASE" -c "$COPY_SQL" > "$OUT"

echo "Exportado: $OUT"
