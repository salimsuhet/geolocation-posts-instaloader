"""
Coleta de posts Instagram georreferenciados - Grande Vitória ES

Variáveis de controle (.env):
  COLLECT_MODE          both | location | hashtag
  HASHTAG_AUTO_GENERATE true | false
"""

import logging
import os

import instaloader

from .config import (
    BBOX,
    COLLECT_MODE,
    HASHTAG_AUTO_GENERATE,
    INSTALOADER_SESSION_DIR,
    INSTALOADER_USERNAME,
    LOCATION_RESOLVE_MODE,
)
from .db import get_conn, insert_locations
from .hashtags import build_hashtag_list
from .instagram import collect_posts, collect_posts_by_hashtag, resolve_location_ids, resolve_location_ids_geo_grid
from .osm import fetch_osm_locations

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/collector.log"),
    ],
)
log = logging.getLogger(__name__)


def main():
    log.info(f"Modo de coleta       : {COLLECT_MODE}")
    log.info(f"Modo resolução loc.  : {LOCATION_RESOLVE_MODE}")
    log.info(f"Hashtags automáticas : {'sim' if HASHTAG_AUTO_GENERATE else 'não'}")
    log.info(f"Bounding box         : lat [{BBOX[0]}, {BBOX[2]}] lon [{BBOX[1]}, {BBOX[3]}]")

    conn = get_conn()

    L = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        save_metadata=False,
        quiet=True,
        request_timeout=30,
    )

    if INSTALOADER_USERNAME:
        session_file = (
            os.path.join(INSTALOADER_SESSION_DIR, f"session-{INSTALOADER_USERNAME}")
            if INSTALOADER_SESSION_DIR else None
        )
        try:
            L.load_session_from_file(INSTALOADER_USERNAME, filename=session_file)
            log.info(f"Sessão carregada para @{INSTALOADER_USERNAME}")
        except FileNotFoundError:
            log.warning(
                f"Sessão não encontrada para @{INSTALOADER_USERNAME} — "
                "continuando sem login (rate limit mais agressivo)."
            )

    # ── Fase 1: locations ─────────────────────────────────────
    osm_locations = []
    if COLLECT_MODE in ("both", "location"):
        log.info("=== Fase 1: coleta por locations ===")

        if LOCATION_RESOLVE_MODE == "geo_grid":
            log.info("Modo: geo_grid (grade de coordenadas via location_search)")
            ig_locations = resolve_location_ids_geo_grid(conn=conn)
        else:
            log.info("Modo: osm_name (nome OSM → fbsearch/places)")
            osm_locations = fetch_osm_locations()
            ig_locations  = resolve_location_ids(L, osm_locations, conn=conn)

        insert_locations(conn, ig_locations)
        collect_posts(L, conn, ig_locations)
    else:
        log.info("=== Fase 1 ignorada (COLLECT_MODE=hashtag) ===")

    # ── Fase 2: hashtags ──────────────────────────────────────
    if COLLECT_MODE in ("both", "hashtag"):
        log.info("=== Fase 2: coleta por hashtags ===")

        # Carrega POIs para geração automática somente se necessário
        if HASHTAG_AUTO_GENERATE and not osm_locations:
            log.info("Carregando POIs para geração automática de hashtags...")
            osm_locations = fetch_osm_locations()

        hashtags = build_hashtag_list(
            osm_locations if HASHTAG_AUTO_GENERATE else []
        )
        collect_posts_by_hashtag(L, conn, hashtags)
    else:
        log.info("=== Fase 2 ignorada (COLLECT_MODE=location) ===")

    conn.close()
    log.info("Coleta finalizada.")


if __name__ == "__main__":
    main()
