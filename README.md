# Instagram Geolocation Collector — Grande Vitória ES

Coleta posts do Instagram dentro de um bounding box configurável por duas
fontes complementares, aplicando **todos os 4 métodos de geolocalização** a
cada post para análise de correlação.

| Fonte       | Como funciona                                              |
|-------------|-------------------------------------------------------------|
| `location`  | Descobre location IDs → coleta posts por location           |
| `hashtag`   | Lista fixa + gerada dos POIs → coleta posts por hashtag     |

Dois modos de descoberta de locations:

| `LOCATION_RESOLVE_MODE` | Como descobre os IDs                                      |
|-------------------------|-----------------------------------------------------------|
| `osm_name`              | OSM → busca por nome via fbsearch/places (padrão)         |
| `geo_grid`              | Grade de coordenadas sobre a BBOX via location_search     |

---

## Pré-requisitos

- Docker Desktop (Windows/Mac) ou Docker + Docker Compose (Linux)
- Python 3 instalado no host — **só para gerar a sessão do Instaloader**

---

## 1. Baixar a base OpenStreetMap

O coletor usa um arquivo `.pbf` local para extrair os POIs da região.

Acesse **https://download.geofabrik.de/south-america/brazil.html** e baixe
o arquivo desejado:

```
espirito-santo-latest.osm.pbf   (~30 MB)
sudeste-latest.osm.pbf          (~1 GB)
```

Salve na raiz do projeto. O coletor vai gerar automaticamente um
`*.osm.filtered.pbf` recortado pelo BBOX na primeira execução.

> Se o `.pbf` não for encontrado, o coletor usa a Overpass API como
> fallback (mais lento e sujeito a timeout).

---

## 2. Gerar a sessão do Instaloader (uma vez)

A sessão autentica o coletor no Instagram e evita rate limit agressivo.

### Por que criar no Windows e não no container?

O Instagram vincula a sessão ao user-agent do ambiente onde ela foi criada.
Se você criar a sessão dentro do container (Linux) e o Instagram bloquear
por suspeita de bot, a sessão fica inutilizável. Criando no Windows com o
Python instalado localmente, o user-agent do browser é usado, o que é mais
confiável.

### Passo a passo (Windows)

**1. Instale o instaloader no host** (se ainda não tiver):

```powershell
pip install instaloader
```

**2. Crie a pasta de sessão** na raiz do projeto:

```powershell
mkdir session
```

**3. Faça login e salve a sessão** na pasta criada:

```powershell
python -m instaloader --login SEU_USUARIO --sessionfile .\session\session-SEU_USUARIO
```

O comando vai pedir:
- **Senha** do Instagram
- **Código 2FA** (se ativado na conta) — abra o app autenticador e cole o código

Exemplo com usuário real:
```powershell
python -m instaloader --login salimsuhet --sessionfile .\session\session-salimsuhet
```

Saída esperada:
```
Logged in as salimsuhet.
Saved session to .\session\session-salimsuhet.
```

**4. Configure o caminho no `.env`** (use o caminho absoluto):

```dotenv
INSTALOADER_USERNAME=salimsuhet
INSTALOADER_SESSION_PATH=C:\Users\SeuUsuario\Documents\GitHub\seu-projeto\session
```

> ⚠️ Use sempre o **caminho absoluto** — o Docker Desktop no Windows não
> resolve caminhos relativos (`.\session`) em volumes corretamente.

**A sessão expira periodicamente.** Repita o passo 3 se o coletor emitir:
```
401 Unauthorized — Please wait a few minutes
feedback_required / spam: true
```

---

## 3. Obter o Cookie do Instagram (para `geo_grid`)

Necessário apenas se `LOCATION_RESOLVE_MODE=geo_grid`.

O modo `geo_grid` usa o endpoint `location_search` do Instagram diretamente,
que requer o cookie completo do browser (não a sessão do Instaloader).

### Passo a passo

**1.** Abra o **Google Chrome** e acesse **https://www.instagram.com**

**2.** Faça login com sua conta (se ainda não estiver logado)

**3.** Pressione **F12** para abrir o DevTools

**4.** Clique na aba **Network** (Rede)

**5.** Recarregue a página com **F5** — aparecerão várias requisições

**6.** Clique em qualquer requisição para `www.instagram.com`

**7.** Na aba **Headers**, role até **Request Headers**

**8.** Localize o campo **`cookie:`** e copie todo o valor (é uma string longa)

**9.** Cole no `.env`:

```dotenv
LOCATION_RESOLVE_MODE=geo_grid
IG_COOKIE=sessionid=XXXXX; csrftoken=XXXXX; ds_user_id=XXXXX; ...
GEO_GRID_STEP_KM=1.0
```

> ⚠️ O cookie contém credenciais sensíveis — nunca commite o `.env`.
> O cookie expira com o tempo; repita se o coletor apresentar erros 401.

---

## 4. Configurar variáveis de ambiente

Copie o arquivo de exemplo:

```powershell
copy .env.example .env
```

Edite o `.env` com os seus valores:

```dotenv
# --- Instagram --------------------------------------------------
INSTALOADER_USERNAME=seu_usuario
# Caminho ABSOLUTO da pasta session/ do projeto
INSTALOADER_SESSION_PATH=C:\Users\SeuUsuario\Documents\GitHub\seu-projeto\session

# --- OpenStreetMap (.pbf) ---------------------------------------
OSM_PBF_DIR=.
OSM_PBF_FILE=espirito-santo-latest.osm.pbf

# --- Bounding box -----------------------------------------------
# Formato: lat_min,lon_min,lat_max,lon_max
BBOX=-20.5,-40.5,-20.1,-40.1

# --- Modo de resolução de locations -----------------------------
# osm_name = busca por nome OSM (padrão)
# geo_grid  = grade de coordenadas (requer IG_COOKIE)
LOCATION_RESOLVE_MODE=osm_name

# Preencha apenas se LOCATION_RESOLVE_MODE=geo_grid:
IG_COOKIE=
GEO_GRID_STEP_KM=1.0

# --- Modo de coleta ---------------------------------------------
# both | location | hashtag
COLLECT_MODE=both

# --- Período de coleta ------------------------------------------
STOP_DATE=2026-01-01

# --- Hashtags automáticas ---------------------------------------
HASHTAG_AUTO_GENERATE=true

# --- Banco de dados ---------------------------------------------
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=instagram
DB_PORT=5432
```

---

## 5. Ajustar as hashtags fixas (opcional)

Edite `hashtags.txt` na raiz do projeto. O coletor combina essas hashtags
com as geradas automaticamente a partir dos POIs do `.pbf`.
Usado apenas quando `COLLECT_MODE=both` ou `hashtag`.

---

## 6. Subir tudo

```powershell
docker-compose up
```

O coletor executa as fases conforme `COLLECT_MODE`:

| `COLLECT_MODE` | Fase 1 (locations)                        | Fase 2 (hashtags) |
|----------------|-------------------------------------------|-------------------|
| `both`         | ✅                                         | ✅                 |
| `location`     | ✅                                         | ❌                 |
| `hashtag`      | ❌ (carrega POIs só para gerar hashtags)   | ✅                 |

Comandos úteis:

```powershell
# acompanhar logs em tempo real
docker-compose logs -f collector

# verificar posts coletados
docker exec -it gv_instagram_db psql -U postgres -d instagram -c "SELECT COUNT(*) FROM ig_posts;"

# parar tudo preservando os dados
docker-compose down

# parar tudo e apagar o banco (zera tudo)
docker-compose down -v
```

---

## Modos de resolução de locations

### `osm_name` (padrão)

Extrai POIs do `.pbf`, busca cada nome no endpoint `fbsearch/places` do
Instagram e resolve o `location_id` correspondente. Mais lento (~10s por POI)
mas correlaciona diretamente com o OSM.

```dotenv
LOCATION_RESOLVE_MODE=osm_name
```

### `geo_grid` (Bellingcat)

Varre uma grade de pontos sobre o BBOX usando o endpoint `location_search`
do Instagram. Retorna todas as locations registradas naquela área sem depender
de match por nome. Mais rápido e completo, mas requer o cookie do browser.

```dotenv
LOCATION_RESOLVE_MODE=geo_grid
IG_COOKIE=<cookie copiado do DevTools>
GEO_GRID_STEP_KM=1.0
```

Estimativa de pontos na grade para a Grande Vitória (40×40 km):

| `GEO_GRID_STEP_KM` | Pontos na grade | Tempo estimado |
|--------------------|-----------------|----------------|
| `2.0`              | ~400            | ~10 min        |
| `1.0`              | ~1600           | ~30 min        |
| `0.5`              | ~6400           | ~2 h           |

---

## Configuração avançada

### Período de coleta (`STOP_DATE`)

Posts anteriores a essa data são ignorados. Padrão: `2026-01-01`.

```dotenv
STOP_DATE=2025-01-01
```

### Bounding box

Usado para filtrar POIs do `.pbf`, descartar posts fora da área e calcular
o método `bbox_centroid`.

```dotenv
# Grande Vitória completa
BBOX=-20.5,-40.5,-20.1,-40.1

# Só Vitória
BBOX=-20.35,-40.40,-20.25,-40.28
```

### Dividir em sub-regiões

Para reduzir o tempo da coleta por locations, rode o coletor para cada
sub-região separadamente alterando o `BBOX` entre execuções.

---

## Métodos de geolocalização

| Método               | Fonte                                      | Confiança | Disponível em     |
|----------------------|--------------------------------------------|-----------|-------------------|
| `post_latlon`        | `post.location.lat/lng` direto na API      | 95        | location, hashtag |
| `location_centroid`  | Centroide da IG location do post           | 70        | location          |
| `osm_match`          | Coordenada do POI OSM que gerou o match    | 50        | osm_name          |
| `bbox_centroid`      | Centro do bounding box — sempre disponível | 10        | location, hashtag |

---

## Consultas de análise

Os scripts `run-queries.ps1` (Windows) e `run-queries.sh` (Linux/Mac) executam
as queries SQL da pasta `queries/`.

### Windows (PowerShell)

Na primeira vez, libere a execução de scripts:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

```powershell
# todas as queries
.\run-queries.ps1

# uma query específica
.\run-queries.ps1 -Query method_coverage
.\run-queries.ps1 -Query post_coordinates_detail
.\run-queries.ps1 -Query locations_resolvidas_lista
```

### Linux / Mac (Bash)

```bash
chmod +x run-queries.sh   # só na primeira vez
./run-queries.sh
./run-queries.sh method_coverage
```

### Queries disponíveis

| Arquivo                        | O que mostra                                         |
|-------------------------------|------------------------------------------------------|
| `method_coverage.sql`          | Cobertura de cada método geo (% com coordenada)      |
| `coverage_by_source.sql`       | Posts e métodos por fonte (location vs hashtag)      |
| `post_coordinates_detail.sql`  | Coordenadas dos 4 métodos por post com distâncias    |
| `posts_wide_top_divergence.sql`| Posts com maior divergência entre métodos            |
| `location_divergence.sql`      | Locations onde os métodos mais discordam             |
| `post_by_shortcode.sql`        | Todos os métodos para um post específico             |
| `locations_resolvidas_count.sql` | Total de POIs OSM com match no Instagram           |
| `locations_resolvidas_lista.sql` | Lista de locations resolvidas com coordenadas      |
| `hashtags_automaticas_lista.sql` | Hashtags geradas com contagem de posts             |

### Consultas rápidas

```powershell
# total de posts
docker exec -it gv_instagram_db psql -U postgres -d instagram -c "SELECT COUNT(*) FROM ig_posts;"

# posts por dia
docker exec -it gv_instagram_db psql -U postgres -d instagram -c "SELECT DATE(taken_at) AS dia, COUNT(*) FROM ig_posts GROUP BY dia ORDER BY dia DESC;"

# locations resolvidas
docker exec -it gv_instagram_db psql -U postgres -d instagram -c "SELECT COUNT(*) FROM ig_locations WHERE osm_name IS NOT NULL;"
```

---

## Exportar dados

```powershell
# exportar posts
docker exec -it gv_instagram_db psql -U postgres -d instagram -c "\COPY ig_posts TO '/tmp/ig_posts.csv' CSV HEADER"
docker cp gv_instagram_db:/tmp/ig_posts.csv .\ig_posts.csv

# exportar geolocalizações
docker exec -it gv_instagram_db psql -U postgres -d instagram -c "\COPY ig_post_geolocations TO '/tmp/geolocations.csv' CSV HEADER"
docker cp gv_instagram_db:/tmp/geolocations.csv .\geolocations.csv
```

---

## Estrutura dos arquivos

```
.
├── src/
│   ├── config.py       # variáveis de ambiente (BBOX, COLLECT_MODE, LOCATION_RESOLVE_MODE)
│   ├── db.py           # conexão e inserts no PostgreSQL
│   ├── geo.py          # GeoResult e os 4 métodos de geolocalização
│   ├── hashtags.py     # carrega lista fixa e gera hashtags dos POIs
│   ├── osm.py          # leitura do .pbf local (fallback: Overpass API)
│   ├── instagram.py    # coleta por location e hashtag; resolve location IDs
│   └── main.py         # entrypoint — orquestra as fases
├── migrations/
│   └── 001_initial_schema.sql
├── queries/            # queries SQL prontas para análise
├── session/            # sessão do Instaloader (não commitar)
├── logs/               # logs persistentes (gerado automaticamente)
├── hashtags.txt        ← edite para ajustar as hashtags fixas
├── run-queries.ps1     ← executa queries no Windows
├── run-queries.sh      ← executa queries no Linux/Mac
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── requirements.txt
├── .env.example        ← template de variáveis (commitar)
├── .env                ← criado por você (não commitar)
└── README.md
```
