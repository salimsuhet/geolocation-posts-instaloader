import os
import pathlib as _pathlib
from datetime import datetime, timezone


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
# COLLECT_MODE: "both" | "location" | "hashtag"
#   both     → roda as duas fases (padrão)
#   location → somente coleta por location (OSM → Instagram)
#   hashtag  → somente coleta por hashtag
COLLECT_MODE = os.getenv("COLLECT_MODE", "both").strip().lower()
if COLLECT_MODE not in {"both", "location", "hashtag"}:
    raise ValueError(
        f"COLLECT_MODE inválido: '{COLLECT_MODE}'. "
        "Valores aceitos: both | location | hashtag"
    )

# ─── Geração automática de hashtags ──────────────────────────
# true  → gera hashtags a partir dos nomes dos POIs do .pbf (padrão)
# false → usa apenas a lista fixa do hashtags.txt
HASHTAG_AUTO_GENERATE = os.getenv("HASHTAG_AUTO_GENERATE", "true").strip().lower() == "true"

# ─── Rate limit e batch ───────────────────────────────────────
# topsearch: endpoint mais sensível a bloqueio, usar ritmo conservador
REQUESTS_PER_MINUTE_SEARCH = 6
BASE_SLEEP_SEARCH = 60 / REQUESTS_PER_MINUTE_SEARCH   # ~10 s entre buscas

# coleta de posts/hashtags: endpoint menos restritivo
REQUESTS_PER_MINUTE = 15
BASE_SLEEP = 60 / REQUESTS_PER_MINUTE                 # ~4 s entre posts

BATCH_SIZE = 50

# ─── Período de coleta ────────────────────────────────────────
# Coleta posts até esta data (exclusive)
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

# Cookie do Instagram (necessário apenas para LOCATION_RESOLVE_MODE=geo_grid)
# Obter em: DevTools → Network → qualquer request → Request Headers → cookie
IG_COOKIE = os.getenv("IG_COOKIE", "")

# Espaçamento da grade em km (LOCATION_RESOLVE_MODE=geo_grid)
# 1.0 km → ~1600 pontos para Grande Vitória (40×40 km)
# 0.5 km → ~6400 pontos (mais completo, mais lento)
GEO_GRID_STEP_KM = float(os.getenv("GEO_GRID_STEP_KM", "1.0"))

# ─── Instagram ────────────────────────────────────────────────
INSTALOADER_USERNAME    = os.getenv("INSTALOADER_USERNAME")
INSTALOADER_SESSION_DIR = os.getenv("INSTALOADER_SESSION_DIR")
