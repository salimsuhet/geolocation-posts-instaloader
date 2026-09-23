import os
import pathlib as _pathlib
import re as _re
from datetime import datetime, timezone
from datetime import time as _time
from zoneinfo import ZoneInfo as _ZoneInfo


# ─── Banco de dados ───────────────────────────────────────────
DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     int(os.getenv("DB_PORT", "5432")),
    "dbname":   os.getenv("DB_NAME",     "instagram"),
    "user":     os.getenv("DB_USER",     "postgres"),
    "password": os.getenv("DB_PASSWORD", "postgres"),
}

# ─── Overpass (fallback quando não há .pbf) ───────────────────
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# ─── Bounding box ─────────────────────────────────────────────
# Lido do .env; padrão = Grande Vitória (lat_min, lon_min, lat_max, lon_max)
def _bbox() -> tuple[float, float, float, float]:
    raw = os.getenv("BBOX", "-20.5,-40.5,-20.1,-40.1")
    try:
        parts = [float(x.strip()) for x in raw.split(",")]
        if len(parts) != 4:
            raise ValueError
        return tuple(parts)
    except ValueError:
        raise ValueError(
            f"BBOX inválido: '{raw}'. "
            "Formato esperado: 'lat_min,lon_min,lat_max,lon_max' "
            "ex: -20.5,-40.5,-20.1,-40.1"
        )

BBOX = _bbox()
BBOX_CENTER_LAT = (BBOX[0] + BBOX[2]) / 2
BBOX_CENTER_LON = (BBOX[1] + BBOX[3]) / 2

# ─── Modo de coleta ───────────────────────────────────────────
# COLLECT_MODE: "both" | "location" | "hashtag" | "geo_grid_scan"
#   both           → roda as duas fases (padrão)
#   location       → somente coleta por location (OSM → Instagram)
#   hashtag        → somente coleta por hashtag
#   geo_grid_scan  → só varre a grade geo_grid e salva locations; não coleta posts
#                    (requer LOCATION_RESOLVE_MODE=geo_grid)
COLLECT_MODE = os.getenv("COLLECT_MODE", "both").strip().lower()
if COLLECT_MODE not in {"both", "location", "hashtag", "geo_grid_scan"}:
    raise ValueError(
        f"COLLECT_MODE inválido: '{COLLECT_MODE}'. "
        "Valores aceitos: both | location | hashtag | geo_grid_scan"
    )

# ─── Geração automática de hashtags ──────────────────────────
# true  → gera hashtags a partir dos nomes dos POIs do .pbf (padrão)
# false → usa apenas a lista fixa do hashtags.txt
HASHTAG_AUTO_GENERATE = os.getenv("HASHTAG_AUTO_GENERATE", "true").strip().lower() == "true"

# ─── Rate limit customizável (busca de locations) ──────────────
# Tempo aleatório entre T_MIN e T_MAX (segundos) para cada chamada
# de busca de location (fbsearch/places e location_search/geo_grid).
# Use valores altos se o Instagram estiver bloqueando por excesso
# de requisições (ex: T_MIN=15, T_MAX=30).
T_MIN_SEARCH = float(os.getenv("T_MIN_SEARCH", "8"))
T_MAX_SEARCH = float(os.getenv("T_MAX_SEARCH", "16"))
if T_MIN_SEARCH > T_MAX_SEARCH:
    raise ValueError(
        f"T_MIN_SEARCH ({T_MIN_SEARCH}) não pode ser maior que "
        f"T_MAX_SEARCH ({T_MAX_SEARCH})"
    )

# ─── Rate limit customizável (coleta de posts/hashtags/locations) ──
# Tempo aleatório entre T_MIN_POST e T_MAX_POST (segundos) após cada post
# processado e após cada location/hashtag visitada (mesmo sem posts).
# Endpoint menos restritivo que a busca de locations (T_MIN_SEARCH acima),
# por isso o padrão é mais rápido — mas pode ser aumentado do mesmo jeito
# se o Instagram começar a bloquear por excesso de requisições.
T_MIN_POST = float(os.getenv("T_MIN_POST", "2.8"))
T_MAX_POST = float(os.getenv("T_MAX_POST", "6.0"))
if T_MIN_POST > T_MAX_POST:
    raise ValueError(
        f"T_MIN_POST ({T_MIN_POST}) não pode ser maior que "
        f"T_MAX_POST ({T_MAX_POST})"
    )

# ─── Rate limit e batch ───────────────────────────────────────
# topsearch: endpoint mais sensível a bloqueio, usar ritmo conservador
REQUESTS_PER_MINUTE_SEARCH = 6
BASE_SLEEP_SEARCH = 60 / REQUESTS_PER_MINUTE_SEARCH   # ~10 s entre buscas

BATCH_SIZE = 50

# ─── Período de coleta ────────────────────────────────────────
# Coleta posts até esta data (exclusive) — limite inferior (mais antigo)
# Formato no .env: STOP_DATE=2026-01-01
def _stop_date() -> datetime:
    raw = os.getenv("STOP_DATE", "2026-01-01")
    try:
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValueError(
            f"STOP_DATE inválido: '{raw}'. "
            "Formato esperado: YYYY-MM-DD ex: 2026-01-01"
        )

STOP_DATE = _stop_date()

# Limite superior (mais recente) do período de coleta — opcional.
# Posts mais recentes que essa data são ignorados (não inseridos no banco),
# mas a iteração continua (o Instagram devolve do mais recente pro mais
# antigo) até alcançar a janela [STOP_DATE, START_DATE] ou STOP_DATE.
# Deixe em branco para não limitar (padrão: sem teto, pega até o post mais
# recente de cada location/hashtag).
# Formato no .env: START_DATE=2026-07-24
def _start_date():
    raw = os.getenv("START_DATE", "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValueError(
            f"START_DATE inválido: '{raw}'. "
            "Formato esperado: YYYY-MM-DD ex: 2026-07-24"
        )

START_DATE = _start_date()
if START_DATE is not None and START_DATE <= STOP_DATE:
    raise ValueError(
        f"START_DATE ({START_DATE.date()}) deve ser posterior a "
        f"STOP_DATE ({STOP_DATE.date()})"
    )

# ─── OSM / PBF ────────────────────────────────────────────────
_OSM_PBF_DIR  = _pathlib.Path(os.getenv("OSM_PBF_DIR", "."))
_OSM_PBF_FILE = os.getenv("OSM_PBF_FILE", "espirito-santo-latest.osm.pbf")

# OSM_PBF_PATH pode vir direto do ambiente (ex: docker-compose injeta
# /data/<arquivo>); caso contrário, monta a partir de DIR + FILE.
OSM_PBF_PATH: str = os.getenv("OSM_PBF_PATH") or str(_OSM_PBF_DIR / _OSM_PBF_FILE)

# Arquivo de saída filtrado pelo BBOX — sempre ao lado do original
#   ex: /data/sudeste-260602.osm.pbf  →  /data/sudeste-260602.osm.filtered.pbf
_osm_stem = _OSM_PBF_FILE[: _OSM_PBF_FILE.index(".osm")]
OSM_PBF_FILTERED_PATH: str = str(_pathlib.Path(OSM_PBF_PATH).parent / f"{_osm_stem}.osm.filtered.pbf")

# ─── Modo de resolução de locations ──────────────────────────
# osm_name  = resolve por nome via OSM + fbsearch/places (padrão)
# geo_grid  = varre grade de coordenadas via location_search (bellingcat)
LOCATION_RESOLVE_MODE = os.getenv("LOCATION_RESOLVE_MODE", "osm_name").strip().lower()
if LOCATION_RESOLVE_MODE not in {"osm_name", "geo_grid"}:
    raise ValueError(
        f"LOCATION_RESOLVE_MODE inválido: '{LOCATION_RESOLVE_MODE}'. "
        "Valores aceitos: osm_name | geo_grid"
    )

# Cookie do Instagram — fallback manual para LOCATION_RESOLVE_MODE=geo_grid.
# Só é necessário se INSTALOADER_ACCOUNTS/INSTALOADER_USERNAME estiver vazio:
# com uma conta configurada, o cookie é derivado automaticamente da sessão
# ativa do Instaloader (ver src/accounts.py), sem precisar colar manualmente.
# Obter em: DevTools → Network → qualquer request → Request Headers → cookie
IG_COOKIE = os.getenv("IG_COOKIE", "")

# Espaçamento da grade em km (LOCATION_RESOLVE_MODE=geo_grid)
# 1.0 km → ~1600 pontos para Grande Vitória (40×40 km)
# 0.5 km → ~6400 pontos (mais completo, mais lento)
GEO_GRID_STEP_KM = float(os.getenv("GEO_GRID_STEP_KM", "1.0"))

# Endpoint(s) usados na varredura geo_grid para consultar cada ponto:
#   mobile = i.instagram.com/api/v1/location_search (API do app mobile)
#   web    = www.instagram.com/location_search (técnica original do Bellingcat)
#   both   = tenta mobile primeiro; só tenta web se o mobile falhar (padrão)
# Algumas contas têm um dos dois endpoints bloqueado/restrito mesmo com
# cookie válido — "both" dá resiliência tentando o outro antes de desistir
# do ponto.
GEO_GRID_ENDPOINT_MODE = os.getenv("GEO_GRID_ENDPOINT_MODE", "both").strip().lower()
if GEO_GRID_ENDPOINT_MODE not in {"mobile", "web", "both"}:
    raise ValueError(
        f"GEO_GRID_ENDPOINT_MODE inválido: '{GEO_GRID_ENDPOINT_MODE}'. "
        "Valores aceitos: mobile | web | both"
    )

# ─── Instagram ────────────────────────────────────────────────
INSTALOADER_USERNAME    = os.getenv("INSTALOADER_USERNAME")
INSTALOADER_SESSION_DIR = os.getenv("INSTALOADER_SESSION_DIR")

# ─── Contas Instagram (rotação) ────────────────────────────────
# Lista de usernames para rotacionar entre si durante a coleta (1 a 10
# contas). Cada uma precisa ter sessão salva previamente via
# `scripts/login_accounts.py` em INSTALOADER_SESSION_DIR (arquivo
# session-<username> — mesmo formato que o Instaloader já usa).
# Se vazia, cai no INSTALOADER_USERNAME único (compatibilidade).
def _accounts() -> list[str]:
    raw = os.getenv("INSTALOADER_ACCOUNTS", "").strip()
    if raw:
        accounts = [u.strip() for u in raw.split(",") if u.strip()]
    elif INSTALOADER_USERNAME:
        accounts = [INSTALOADER_USERNAME]
    else:
        accounts = []
    if len(accounts) > 10:
        raise ValueError(
            f"INSTALOADER_ACCOUNTS tem {len(accounts)} contas — máximo suportado é 10."
        )
    return accounts

INSTALOADER_ACCOUNTS = _accounts()

# Duração (horas) que cada conta fica ativa antes de rotacionar para a
# próxima — sorteada uniformemente entre MIN e MAX a cada troca.
ACCOUNT_ROTATE_MIN_HOURS = float(os.getenv("ACCOUNT_ROTATE_MIN_HOURS", "1"))
ACCOUNT_ROTATE_MAX_HOURS = float(os.getenv("ACCOUNT_ROTATE_MAX_HOURS", "6"))
if ACCOUNT_ROTATE_MIN_HOURS > ACCOUNT_ROTATE_MAX_HOURS:
    raise ValueError(
        f"ACCOUNT_ROTATE_MIN_HOURS ({ACCOUNT_ROTATE_MIN_HOURS}) não pode ser maior que "
        f"ACCOUNT_ROTATE_MAX_HOURS ({ACCOUNT_ROTATE_MAX_HOURS})"
    )

# ─── Janela de horário de coleta ───────────────────────────────
# Restringe a coleta a um intervalo de horário (e dias da semana), para
# que o tráfego se misture ao uso normal da rede de onde o coletor roda
# (ex: horário comercial de uma instituição). Fora da janela, o coletor
# pausa e retoma sozinho quando ela reabrir — não encerra o processo.
# Deixe COLLECT_WINDOW_START/END em branco para não restringir horário.
def _parse_hhmm(raw: str, label: str) -> _time | None:
    raw = raw.strip()
    if not raw:
        return None
    if not _re.fullmatch(r"\d{2}:\d{2}", raw):
        raise ValueError(f"{label} inválido: '{raw}'. Formato esperado: HH:MM ex: 08:00")
    h, m = (int(x) for x in raw.split(":"))
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"{label} inválido: '{raw}'. Formato esperado: HH:MM ex: 08:00")
    return _time(h, m)

COLLECT_WINDOW_START = _parse_hhmm(os.getenv("COLLECT_WINDOW_START", "08:00"), "COLLECT_WINDOW_START")
COLLECT_WINDOW_END   = _parse_hhmm(os.getenv("COLLECT_WINDOW_END", "19:00"), "COLLECT_WINDOW_END")
if (COLLECT_WINDOW_START is None) != (COLLECT_WINDOW_END is None):
    raise ValueError(
        "COLLECT_WINDOW_START e COLLECT_WINDOW_END devem ser definidos juntos "
        "(ou ambos vazios para não restringir horário)."
    )

# Dias da semana em que a janela vale: "mon-fri" (padrão), "all", ou lista
# separada por vírgula (ex: "mon,wed,fri"). Abreviações em inglês (3 letras).
_WEEKDAY_NAMES = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_WEEKDAY_LABELS = {v: k for k, v in _WEEKDAY_NAMES.items()}

def _parse_window_days(raw: str) -> set[int]:
    raw = raw.strip().lower()
    if not raw or raw == "all":
        return set(range(7))
    if "-" in raw and "," not in raw:
        start_s, end_s = (p.strip() for p in raw.split("-", 1))
        if start_s not in _WEEKDAY_NAMES or end_s not in _WEEKDAY_NAMES:
            raise ValueError(
                f"COLLECT_WINDOW_DAYS inválido: '{raw}'. "
                "Use mon-fri, all, ou lista tipo mon,wed,fri"
            )
        start, end = _WEEKDAY_NAMES[start_s], _WEEKDAY_NAMES[end_s]
        if start <= end:
            return set(range(start, end + 1))
        return set(range(start, 7)) | set(range(0, end + 1))
    days = set()
    for part in raw.split(","):
        part = part.strip()
        if part not in _WEEKDAY_NAMES:
            raise ValueError(
                f"COLLECT_WINDOW_DAYS inválido: '{raw}'. "
                "Use mon-fri, all, ou lista tipo mon,wed,fri"
            )
        days.add(_WEEKDAY_NAMES[part])
    return days

COLLECT_WINDOW_DAYS = _parse_window_days(os.getenv("COLLECT_WINDOW_DAYS", "mon-fri"))

# Timezone usada para avaliar a janela — explícita e independente do
# relógio/timezone do sistema operacional onde o processo roda (container
# costuma rodar em UTC). Requer o pacote `tzdata` no requirements.txt para
# funcionar em qualquer ambiente, inclusive Windows.
COLLECT_WINDOW_TZ = os.getenv("COLLECT_WINDOW_TZ", "America/Sao_Paulo").strip()
try:
    _ZoneInfo(COLLECT_WINDOW_TZ)
except Exception as e:
    raise ValueError(f"COLLECT_WINDOW_TZ inválido: '{COLLECT_WINDOW_TZ}' ({e})")
