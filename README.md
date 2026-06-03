# Instagram Geolocation Collector — Grande Vitória ES

Coleta posts do Instagram dentro de um bounding box configurável por duas
fontes complementares, aplicando **todos os 4 métodos de geolocalização** a
cada post para análise de correlação.

| Fonte       | Como funciona                                              |
|-------------|------------------------------------------------------------|
| `location`  | OSM → resolve location ID no Instagram → coleta posts      |
| `hashtag`   | Lista fixa + gerada dos POIs → coleta posts por hashtag    |

---

## Pré-requisitos

- Docker + Docker Compose
- Python 3 no host (apenas para gerar a sessão do Instagram)

---

## 1. Baixar a base OpenStreetMap

O coletor usa um arquivo `.pbf` local para extrair os POIs da região.

Acesse **https://download.geofabrik.de/south-america/brazil.html** e baixe
o arquivo desejado, por exemplo:

```
espirito-santo-latest.osm.pbf   (~30 MB)
sudeste-latest.osm.pbf          (~1 GB)
```

Salve o arquivo na raiz do projeto ou em qualquer diretório — você vai
apontar o caminho no `.env`.

> Se o `.pbf` não for encontrado, o coletor cai automaticamente no
> Overpass API como fallback (mais lento e sujeito a timeout).

---

## 2. Gerar a sessão do Instagram (uma vez)

Sem login o Instagram aplica rate limit agressivo em poucos minutos.
Crie a pasta `session` na raiz do projeto e salve o arquivo de sessão nela:

```bash
mkdir session
```

### Opção A — autenticar no host (requer Python instalado)

```bash
pip install instaloader
instaloader --login SEU_USUARIO --sessionfile ./session/session-SEU_USUARIO
```

### Opção B — autenticar dentro do container (sem Python no host)

Suba apenas o banco em segundo plano e abra um container temporário com
terminal interativo:

```bash
# 1. sobe só o banco
docker-compose up -d db

# 2. abre container com TTY para autenticar
docker-compose run --rm -it collector \
    python -m instaloader --login SEU_USUARIO \
    --sessionfile /session/session-SEU_USUARIO

# 3. sobe tudo normalmente
docker-compose up
```

O arquivo de sessão é salvo em `/session` dentro do container, que é o
volume mapeado para `./session/` no host — disponível nas execuções seguintes.

> A sessão expira periodicamente. Repita o passo 2 se o coletor emitir
> avisos de `401 Unauthorized` ou `Please wait a few minutes`.

---

## 3. Configurar variáveis de ambiente

Copie o arquivo de exemplo e edite os valores:

```bash
cp .env.example .env
```

Edite o `.env`:

```env
# ─── Instagram ────────────────────────────────────────────────
INSTALOADER_USERNAME=SEU_USUARIO
INSTALOADER_SESSION_PATH=./session

# ─── OpenStreetMap (.pbf) ─────────────────────────────────────
OSM_PBF_DIR=.                              # . = raiz do projeto
OSM_PBF_FILE=espirito-santo-latest.osm.pbf

# ─── Bounding box ─────────────────────────────────────────────
# Formato: lat_min,lon_min,lat_max,lon_max
BBOX=-20.5,-40.5,-20.1,-40.1

# ─── Modo de coleta ───────────────────────────────────────────
# both | location | hashtag
COLLECT_MODE=both

# ─── Banco de dados ───────────────────────────────────────────
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=instagram
DB_PORT=5432
```

> **Atenção:** nunca commite o `.env` (já está no `.gitignore`).

---

## 4. Ajustar as hashtags fixas (opcional)

Edite `hashtags.txt` na raiz do projeto. O coletor também gera hashtags
automaticamente a partir dos nomes dos POIs — as duas listas são combinadas
e deduplicadas. Só é usado quando `COLLECT_MODE=both` ou `hashtag`.

---

## 5. Subir tudo

```bash
make up
```

O coletor executa as fases conforme `COLLECT_MODE`:

| `COLLECT_MODE` | Fase 1 (locations) | Fase 2 (hashtags) |
|----------------|--------------------|-------------------|
| `both`         | ✅                  | ✅                 |
| `location`     | ✅                  | ❌                 |
| `hashtag`      | ❌ (só lê POIs para gerar hashtags) | ✅  |

Comandos úteis:

```bash
make db       # sobe apenas o banco em segundo plano
make collect  # roda o coletor uma vez
make logs     # acompanha os logs do coletor
make stop     # para todos os containers
make clean    # para containers e apaga o volume do banco
make help     # lista todos os comandos
```

---

## Configuração avançada

### Período de coleta (`STOP_DATE`)

Definido em `src/config.py` (padrão: `2026-01-01`). Posts anteriores a essa
data são ignorados.

### Bounding box

Configurado via `BBOX` no `.env`. O mesmo valor é usado para:
- Filtrar POIs extraídos do `.pbf`
- Descartar posts de hashtag com coordenada fora da área
- Calcular o centroide para o método `bbox_centroid`

---

## Métodos de geolocalização

| Método               | Fonte                                      | Confiança | Disponível em     |
|----------------------|--------------------------------------------|-----------|-------------------|
| `post_latlon`        | `post.location.lat/lng` direto na API      | 95        | location, hashtag |
| `location_centroid`  | Centroide da IG location do post           | 70        | location          |
| `osm_match`          | Coordenada do POI OSM que gerou o match    | 50        | location          |
| `bbox_centroid`      | Centro do bounding box — sempre disponível | 10        | location, hashtag |

---

## Consultas de análise

Os scripts `run-queries.ps1` (Windows) e `run-queries.sh` (Linux/Mac) executam
as queries SQL da pasta `queries/` contra o banco, copiando cada arquivo para
dentro do container automaticamente.

### Windows (PowerShell)

Na primeira vez, libere a execução de scripts para a sessão atual:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Rodar todas as queries:

```powershell
.\run-queries.ps1
```

Rodar uma query específica (por nome parcial):

```powershell
.\run-queries.ps1 -Query method_coverage
.\run-queries.ps1 -Query post_coordinates_detail
```

Container ou banco customizado:

```powershell
.\run-queries.ps1 -Container meu_db -Database meu_banco -User meu_user
```

### Linux / Mac (Bash)

```bash
chmod +x run-queries.sh   # só na primeira vez
./run-queries.sh
./run-queries.sh method_coverage
```

Container customizado via variável de ambiente:

```bash
CONTAINER=meu_db ./run-queries.sh
```

### Queries disponíveis

| Arquivo | O que mostra |
|---|---|
| `method_coverage.sql` | Cobertura de cada método geo (% com coordenada) |
| `coverage_by_source.sql` | Posts e métodos por fonte (location vs hashtag) |
| `post_coordinates_detail.sql` | Coordenadas dos 4 métodos por post com distâncias |
| `posts_wide_top_divergence.sql` | Posts com maior divergência entre métodos |
| `location_divergence.sql` | Locations onde os métodos mais discordam |
| `post_by_shortcode.sql` | Todos os métodos para um post específico |

### Consultas rápidas sem script

```powershell
# total de posts
docker exec -it gv_instagram_db psql -U postgres -d instagram -c "SELECT COUNT(*) FROM ig_posts;"

# posts por hashtag
docker exec -it gv_instagram_db psql -U postgres -d instagram -c "SELECT source_value, COUNT(*) FROM ig_posts WHERE source = 'hashtag' GROUP BY source_value ORDER BY COUNT(*) DESC;"

# posts por dia
docker exec -it gv_instagram_db psql -U postgres -d instagram -c "SELECT DATE(taken_at) AS dia, COUNT(*) FROM ig_posts GROUP BY dia ORDER BY dia DESC;"
```

---

## Estrutura dos arquivos

```
.
├── src/
│   ├── config.py       # constantes e variáveis de ambiente (BBOX, COLLECT_MODE)
│   ├── db.py           # conexão e inserts no PostgreSQL
│   ├── geo.py          # GeoResult e os 4 métodos de geolocalização
│   ├── hashtags.py     # carrega lista fixa e gera hashtags dos POIs
│   ├── osm.py          # leitura do .pbf local (fallback: Overpass API)
│   ├── instagram.py    # coleta por location e por hashtag
│   └── main.py         # entrypoint — orquestra as fases conforme COLLECT_MODE
├── migrations/
│   └── 001_initial_schema.sql
├── queries/
│   ├── method_coverage.sql
│   ├── coverage_by_source.sql
│   ├── posts_wide_top_divergence.sql
│   ├── location_divergence.sql
│   └── post_by_shortcode.sql
├── logs/               # logs persistentes (gerado automaticamente)
├── hashtags.txt        ← edite para ajustar as hashtags fixas
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── requirements.txt
├── .env.example        ← template de variáveis (commitar)
├── .env                ← criado por você (não commitar)
└── README.md
```
