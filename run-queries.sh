#!/usr/bin/env bash
# run-queries.sh
# Executa todas as queries do projeto contra o banco gv_instagram_db
# Uso: ./run-queries.sh
#      ./run-queries.sh method_coverage        # roda só uma query
#      CONTAINER=meu_db ./run-queries.sh       # container customizado

set -euo pipefail

QUERY="${1:-}"
CONTAINER="${CONTAINER:-gv_instagram_db}"
DATABASE="${DATABASE:-instagram}"
USER="${USER:-postgres}"
QUERIES_DIR="$(dirname "$0")/queries"

if [[ ! -d "$QUERIES_DIR" ]]; then
    echo "Erro: pasta 'queries/' não encontrada em $(dirname "$0")" >&2
    exit 1
fi

# Filtra por nome se passado como argumento
if [[ -n "$QUERY" ]]; then
    files=$(find "$QUERIES_DIR" -name "*${QUERY}*.sql" | sort)
else
    files=$(find "$QUERIES_DIR" -name "*.sql" | sort)
fi

if [[ -z "$files" ]]; then
    echo "Nenhum arquivo .sql encontrado em $QUERIES_DIR" >&2
    exit 1
fi

for file in $files; do
    name=$(basename "$file")
    echo ""
    echo "$(printf '=%.0s' {1..60})"
    echo "  $name"
    echo "$(printf '=%.0s' {1..60})"

    docker cp "$file" "${CONTAINER}:/tmp/${name}"
    docker exec -it "$CONTAINER" psql -U "$USER" -d "$DATABASE" -f "/tmp/${name}"
done

echo ""
echo "Concluído."
