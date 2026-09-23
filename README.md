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

## 2. Preparar as sessões do Instaloader (uma ou várias contas)

A sessão autentica o coletor no Instagram e evita rate limit agressivo.
O coletor suporta rotacionar entre **1 e 10 contas** durante a coleta —
cada uma fica ativa por uma janela sorteada (`ACCOUNT_ROTATE_MIN_HOURS` a
`ACCOUNT_ROTATE_MAX_HOURS`) antes de passar pra próxima, sem repetir a
mesma conta duas vezes seguidas e sem trocar no meio de uma location/
hashtag/ponto da grade em andamento. Se você só tem uma conta, o mesmo
mecanismo funciona normalmente com `INSTALOADER_USERNAME`.

### Por que preparar no Windows e não no container?

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

**2. Configure as contas no `.env`** (use o caminho absoluto para a sessão):

```dotenv
# uma conta:
INSTALOADER_USERNAME=salimsuhet

# ou várias, para rotação (deixe INSTALOADER_USERNAME em branco):
INSTALOADER_ACCOUNTS=salimsuhet,contasecundaria,contaterciaria

INSTALOADER_SESSION_PATH=C:\Users\SeuUsuario\Documents\GitHub\seu-projeto\session
```

> ⚠️ Use sempre o **caminho absoluto** em `INSTALOADER_SESSION_PATH` — o
> Docker Desktop no Windows não resolve caminhos relativos (`.\session`)
> em volumes corretamente.

**3. Rode o script de preparo de sessões**, que pede login interativo só
das contas que ainda não têm sessão válida (as demais são puladas
automaticamente):

```powershell
python scripts\login_accounts.py
```

O script vai pedir, para cada conta pendente:
- **Senha** do Instagram
- **Código 2FA** (se ativado na conta) — abra o app autenticador e cole o código

Se o Instagram exigir uma verificação de segurança (checkpoint/challenge)
no primeiro login de uma conta nova, o script avisa e você precisa aprovar
manualmente pelo app/e-mail dessa conta antes de rodar o script de novo —
isso não dá pra automatizar.

**O coletor nunca pede login sozinho** — ele só usa sessões já preparadas
por esse script, pra poder rodar desacompanhado por longos períodos. Se
uma sessão expirar durante a coleta, o coletor apenas pula aquela conta da
rotação e registra um aviso no log; rode `scripts\login_accounts.py` de
novo para reativá-la.

**A sessão expira periodicamente.** Repita o passo 3 se o coletor emitir:
```
401 Unauthorized — Please wait a few minutes
feedback_required / spam: true
```

---

## 3. Obter o Cookie do Instagram (para `geo_grid`) — só sem contas configuradas

O modo `geo_grid` usa o endpoint `location_search` do Instagram diretamente,
que requer um cookie de sessão. **Se você já configurou
`INSTALOADER_ACCOUNTS`/`INSTALOADER_USERNAME` (passo 2), pode pular esta
seção** — o cookie é derivado automaticamente da sessão ativa no momento,
sem precisar colar nada manualmente. `IG_COOKIE` só é usado como fallback
manual quando nenhuma conta está configurada.

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
# Ou, para rotacionar entre várias contas (deixe INSTALOADER_USERNAME em branco):
# INSTALOADER_ACCOUNTS=usuario1,usuario2,usuario3
ACCOUNT_ROTATE_MIN_HOURS=1
ACCOUNT_ROTATE_MAX_HOURS=6
# Caminho ABSOLUTO da pasta session/ do projeto
INSTALOADER_SESSION_PATH=C:\Users\SeuUsuario\Documents\GitHub\seu-projeto\session

# --- Janela de horário de coleta ---------------------------------
# Deixe START/END em branco para não restringir horário
COLLECT_WINDOW_START=08:00
COLLECT_WINDOW_END=19:00
COLLECT_WINDOW_DAYS=mon-fri
COLLECT_WINDOW_TZ=America/Sao_Paulo

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

# Pausa aleatória (segundos) entre cada busca de location
T_MIN_SEARCH=8
T_MAX_SEARCH=16

# --- Modo de coleta ---------------------------------------------
# both | location | hashtag
COLLECT_MODE=both

# --- Período de coleta ------------------------------------------
STOP_DATE=2026-01-01
# Opcional: teto do período (deixe em branco para não limitar)
START_DATE=

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
| `geo_grid_scan`| Só varre a grade e salva locations (❌ posts) | ❌              |

> Se `LOCATION_RESOLVE_MODE=geo_grid`, veja a seção
> [Varredura em duas fases](#varredura-em-duas-fases-recomendado) — recomendado
> rodar `make scan-grid` antes de coletar posts.

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

### `geo_grid` ([Bellingcat](https://github.com/bellingcat/instagram-location-search))

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

#### `GEO_GRID_ENDPOINT_MODE`: qual endpoint usar por ponto

O `location_search` do Instagram é acessível por dois domínios diferentes:

| Valor    | Endpoint                                        | Observação |
|----------|--------------------------------------------------|------------|
| `mobile` | `i.instagram.com/api/v1/location_search`          | API do app mobile |
| `web`    | `www.instagram.com/location_search`               | Técnica original do [Bellingcat](https://github.com/bellingcat/instagram-location-search) |
| `both`   | Tenta `mobile` primeiro; só tenta `web` se `mobile` falhar | **Padrão** |

Na prática, algumas contas têm um dos dois endpoints bloqueado/restrito
mesmo com cookie válido (o Instagram devolve a página de login/checkpoint
em vez de JSON, com `status 200` — não é sempre um erro HTTP claro). O modo
`both` dá uma segunda chance ao ponto antes de desistir dele, sem custo
extra na maioria das vezes (só faz a segunda chamada quando a primeira
falha).

```dotenv
GEO_GRID_ENDPOINT_MODE=both
```

#### Varredura em duas fases (recomendado)

A varredura da grade (`location_search` por ponto) e a coleta de posts são
duas fases independentes. Cada ponto da grade já consultado fica registrado
na tabela `ig_geo_grid_scanned` (por `GEO_GRID_STEP_KM`) — reexecuções pulam
os pontos já escaneados e só refazem pontos que falharam por erro de
rede/HTTP. Isso permite interromper e retomar a varredura sem perder
progresso, e reaproveitar o banco como cache em rodadas futuras.

**1. Rode só a varredura**, sem coletar posts:

```powershell
make scan-grid
```

Isso roda o coletor com `COLLECT_MODE=geo_grid_scan` (sem precisar editar o
`.env`), varre a grade inteira e grava todas as locations descobertas em
`ig_locations`.

> `make scan-grid` roda em primeiro plano (`docker compose run`, sem `-d`).
> Fechar o terminal interrompe a varredura, mas nada se perde — como o
> progresso fica salvo ponto a ponto, é só rodar `make scan-grid` de novo
> para retomar de onde parou.

**Acompanhando o progresso:** o log do coletor só imprime uma linha a cada
100 pontos processados (`geo_grid: X/1890 pontos pendentes | Y locations
novas`), não a cada ponto — senão seriam milhares de linhas ao longo de ~28h
de varredura (veja a tabela de tempo estimado acima). Isso significa que o
log pode ficar "parado" por bastante tempo (com `T_MIN_SEARCH=8` /
`T_MAX_SEARCH=100`, ~90 min entre uma atualização e outra) mesmo com a
varredura avançando normalmente por baixo.

Para conferir o progresso real a qualquer momento, sem depender do log,
rode a query `geo_grid_progresso` (mostra quantos pontos já foram
escaneados, total de locations no banco e o horário do último ponto
processado):

```powershell
.\run-queries.ps1 -Query geo_grid_progresso
```
```bash
./run-queries.sh geo_grid_progresso
```

**2. Revise as locations descobertas** exportando um CSV:

```powershell
.\run-export.ps1 -Query geo_grid_locations_lista
```
```bash
./run-export.sh geo_grid_locations_lista
```

Gera `geo_grid_locations_lista.csv` na raiz do projeto com todas as
locations encontradas (nome, coordenadas, se teve match com OSM).

**3. Só depois, colete os posts** dessas locations, ajustando `COLLECT_MODE`
no `.env` para `location` ou `both` e rodando `make collect` — a coleta usa
todas as locations já salvas no banco (o cache completo), não só as
descobertas na última execução da varredura.

#### Qual endpoint busca os posts de cada location

A coleta usa `i.instagram.com/api/v1/locations/{id}/sections/` (API do app
mobile, `tab=recent`) para listar os posts marcados numa location — o mesmo
comportamento de tocar numa location tag no app e ver os posts recentes de
qualquer usuário que marcou aquele lugar (não é o feed do dono/página do
local). O endpoint web equivalente (`explore/locations/{id}/?__a=1`, usado
pela versão antiga do Instaloader) parou de responder com JSON para
algumas contas — devolve a página HTML normal do site mesmo com sessão
válida.

A paginação usa o cursor `next_max_id` que a própria resposta devolve — os
campos `next_page`/`next_media_ids` desse endpoint não são cursores reais
(ficam vazios ou estáticos).

Cada location cujos posts já foram coletados fica marcada em
`ig_locations.posts_collected_at` — uma reexecução após crash/interrupção
retoma só pelas locations pendentes, sem revisitar as já processadas.

### Controlar o ritmo das requisições

O coletor usa dois pares independentes de `T_MIN`/`T_MAX`, um para cada
tipo de chamada — assim dá pra deixar a busca de locations bem conservadora
sem deixar a coleta de posts desnecessariamente lenta (ou vice-versa).

#### Busca de locations (`T_MIN_SEARCH` / `T_MAX_SEARCH`)

Cada busca de location (`fbsearch/places` no modo `osm_name` ou
`location_search` no modo `geo_grid`) aguarda um tempo aleatório entre
`T_MIN_SEARCH` e `T_MAX_SEARCH` segundos antes da próxima chamada.

```dotenv
T_MIN_SEARCH=8
T_MAX_SEARCH=16
```

Se o Instagram bloquear a conta com `401 Unauthorized`, `429 Too Many
Requests` ou `feedback_required` (spam), aumente esses valores antes de
tentar novamente:

```dotenv
# mais conservador — útil após um bloqueio
T_MIN_SEARCH=20
T_MAX_SEARCH=40
```

#### Coleta de posts (`T_MIN_POST` / `T_MAX_POST`)

Depois de cada post processado (e depois de cada location/hashtag
visitada, mesmo quando ela não tem posts) o coletor aguarda um tempo
aleatório entre `T_MIN_POST` e `T_MAX_POST` segundos. É o endpoint menos
restritivo, por isso o padrão é bem mais rápido que o de busca:

```dotenv
T_MIN_POST=2.8
T_MAX_POST=6.0
```

Se notar bloqueios durante a coleta de posts (não durante a busca de
locations), aumente esses valores do mesmo jeito:

```dotenv
# mais conservador — útil após um bloqueio na coleta de posts
T_MIN_POST=10
T_MAX_POST=20
```

Valores mais altos (em qualquer um dos dois pares) reduzem o risco de
bloqueio mas aumentam o tempo total. Se o bloqueio persistir mesmo com
valores altos, a conta já pode estar marcada — nesse caso, espere 24–48h
sem rodar o coletor antes de tentar de novo.

---

## Configuração avançada

### Rotação de contas e janela de horário

Duas configurações complementares para reduzir a chance de bloqueio quando
a coleta roda por longos períodos:

**Rotação entre contas** (`INSTALOADER_ACCOUNTS`, `ACCOUNT_ROTATE_MIN_HOURS`,
`ACCOUNT_ROTATE_MAX_HOURS`) — em vez de uma única conta fazendo todas as
requisições, o coletor alterna entre até 10 contas, cada uma ativa por uma
duração sorteada (padrão: 1 a 6 horas) antes de passar para a próxima. A
troca só acontece entre unidades de trabalho (location, hashtag ou ponto da
grade geo_grid) — nunca no meio de uma, mesmo que isso deixe a janela real
um pouco maior que a sorteada. Contas sem sessão válida são puladas da
rotação (ver seção 2) sem interromper a coleta.

**Janela de horário** (`COLLECT_WINDOW_START`/`END`/`DAYS`/`TZ`) — restringe
quando o coletor faz requisições ao Instagram, útil para misturar o
tráfego da coleta com o uso normal da rede de onde ela roda (ex: horário
comercial de uma instituição). Fora da janela ou dos dias configurados, o
coletor pausa e retoma sozinho quando ela reabrir — não encerra o processo,
então pode ficar rodando como um serviço de longa duração
(`docker-compose up -d collector`, por exemplo).

```dotenv
COLLECT_WINDOW_START=08:00
COLLECT_WINDOW_END=19:00
COLLECT_WINDOW_DAYS=mon-fri   # ou: all | mon,wed,fri
COLLECT_WINDOW_TZ=America/Sao_Paulo
```

Deixe `COLLECT_WINDOW_START`/`COLLECT_WINDOW_END` em branco para não
restringir horário nenhum.

> A janela é avaliada com uma timezone explícita (`COLLECT_WINDOW_TZ`), não
> com o relógio do sistema operacional — o container roda em UTC por
> padrão, então comparar contra a hora "local" do container daria um
> resultado errado (deslocado pelo fuso). Isso funciona em qualquer
> ambiente (container Linux ou host Windows) sem precisar configurar
> timezone do sistema; o pacote `tzdata` no `requirements.txt` garante a
> base de dados IANA de timezones em qualquer plataforma.

### Período de coleta (`STOP_DATE` / `START_DATE`)

`STOP_DATE` é o limite inferior — posts anteriores a essa data são
ignorados, e a coleta encerra aquela location/hashtag ao alcançá-lo (o
Instagram devolve do mais recente pro mais antigo, então isso funciona
como um ponto de parada). Padrão: `2026-01-01`.

```dotenv
STOP_DATE=2025-01-01
```

`START_DATE` é opcional e define o limite superior, formando uma janela
`[STOP_DATE, START_DATE]`. Posts mais recentes que `START_DATE` são
ignorados (não entram no banco), mas a coleta **continua iterando** até
alcançar a janela — ou seja, reduz o volume salvo e o escopo das
consultas, mas não o número de chamadas necessárias pra pular os posts
mais recentes que a janela. Deixe em branco para não limitar (padrão).

```dotenv
STOP_DATE=2026-07-01
START_DATE=2026-07-24
```

> `START_DATE` deve ser posterior a `STOP_DATE` — o coletor valida isso
> na subida e recusa iniciar se a janela estiver invertida.

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
| `geo_grid_locations_lista.sql`  | Todas as locations descobertas via geo_grid (com ou sem match OSM) |
| `geo_grid_progresso.sql`       | Progresso da varredura geo_grid: pontos escaneados, locations e último ponto processado |
| `coleta_posts_progresso.sql`   | Progresso da coleta de posts: locations coletadas/pendentes, % concluído, total de posts |
| `hashtags_automaticas_lista.sql` | Hashtags geradas com contagem de posts             |
| `limpar_posts_coletados.sql`   | ⚠️ **Destrutiva** — apaga todos os posts/geolocalizações coletados e reseta o cache de progresso da coleta |

### Exportar uma query direto para CSV

Os scripts `run-export.ps1` (Windows) e `run-export.sh` (Linux/Mac) rodam
qualquer query de `queries/` e salvam o resultado como `.csv` local em um
único comando (sem precisar de `docker exec` + `docker cp` manual):

```powershell
.\run-export.ps1 -Query geo_grid_locations_lista
# gera geo_grid_locations_lista.csv na raiz do projeto

.\run-export.ps1 -Query method_coverage -Out coverage.csv
```

```bash
./run-export.sh geo_grid_locations_lista
OUT=coverage.csv ./run-export.sh method_coverage
```

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
│   ├── accounts.py     # rotação entre contas e janela de horário de coleta
│   ├── db.py           # conexão e inserts no PostgreSQL
│   ├── geo.py          # GeoResult e os 4 métodos de geolocalização
│   ├── hashtags.py     # carrega lista fixa e gera hashtags dos POIs
│   ├── osm.py          # leitura do .pbf local (fallback: Overpass API)
│   ├── instagram.py    # coleta por location e hashtag; resolve location IDs
│   └── main.py         # entrypoint — orquestra as fases
├── scripts/
│   └── login_accounts.py  # prepara sessões das contas (login interativo, roda no host)
├── migrations/
│   ├── 001_initial_schema.sql
│   ├── 002_geo_grid_cache.sql             # cache de pontos já escaneados no geo_grid
│   └── 003_locations_collected_cache.sql  # cache de progresso da coleta de posts
├── queries/            # queries SQL prontas para análise
├── session/            # sessões do Instaloader, uma por conta (não commitar)
├── logs/               # logs persistentes (gerado automaticamente)
├── hashtags.txt        ← edite para ajustar as hashtags fixas
├── run-queries.ps1     ← executa queries no Windows
├── run-queries.sh      ← executa queries no Linux/Mac
├── run-export.ps1      ← exporta uma query para .csv no Windows
├── run-export.sh       ← exporta uma query para .csv no Linux/Mac
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── requirements.txt
├── .env.example        ← template de variáveis (commitar)
├── .env                ← criado por você (não commitar)
└── README.md
```
