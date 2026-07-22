.PHONY: up db collect scan-grid logs psql stop clean

up:          ## Sobe banco + coletor (build incluído)
	docker compose up --build

db:          ## Sobe apenas o banco em segundo plano
	docker compose up -d db

collect:     ## Roda o coletor uma vez (banco deve estar no ar)
	docker compose run --rm collector

scan-grid:   ## Roda só a varredura geo_grid (descobre locations, não coleta posts; requer LOCATION_RESOLVE_MODE=geo_grid no .env)
	docker compose run --rm -e COLLECT_MODE=geo_grid_scan collector

logs:        ## Acompanha os logs do coletor em tempo real
	docker compose logs -f collector

psql:        ## Abre o psql dentro do container do banco
	docker compose exec db psql -U postgres -d instagram

stop:        ## Para todos os containers
	docker compose down

clean:       ## Para containers e remove o volume do banco
	docker compose down -v

help:        ## Lista os comandos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
