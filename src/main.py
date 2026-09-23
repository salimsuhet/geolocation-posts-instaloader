"""
Coleta de posts Instagram georreferenciados - Grande Vitória ES

Variáveis de controle (.env):
  COLLECT_MODE          both | location | hashtag | geo_grid_scan
  HASHTAG_AUTO_GENERATE true | false
"""

import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import instaloader

from .accounts import AccountRotator, wait_for_window
from .config import (
    BBOX,
    COLLECT_MODE,
    COLLECT_WINDOW_DAYS,
    COLLECT_WINDOW_END,
    COLLECT_WINDOW_START,
    COLLECT_WINDOW_TZ,
    HASHTAG_AUTO_GENERATE,
    INSTALOADER_ACCOUNTS,
    LOCATION_RESOLVE_MODE,
    START_DATE,
    STOP_DATE,
)
from .db import get_conn, insert_locations, load_uncollected_locations
from .hashtags import build_hashtag_list
from .instagram import collect_posts, collect_posts_by_hashtag, resolve_location_ids, resolve_location_ids_geo_grid
from .osm import fetch_osm_locations

os.makedirs("logs", exist_ok=True)
# Timestamps do log na mesma timezone da janela de coleta, não na do
# container (UTC por padrão).
_LOG_TZ = ZoneInfo(COLLECT_WINDOW_TZ)
logging.Formatter.converter = staticmethod(
    lambda ts: datetime.fromtimestamp(ts, _LOG_TZ).timetuple()
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/collector.log"),
    ],
)
log = logging.getLogger(__name__)


_WEEKDAY_LABELS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def main():
    log.info(f"Modo de coleta       : {COLLECT_MODE}")
    log.info(f"Modo resolução loc.  : {LOCATION_RESOLVE_MODE}")
    log.info(f"Hashtags automáticas : {'sim' if HASHTAG_AUTO_GENERATE else 'não'}")
    log.info(f"Bounding box         : lat [{BBOX[0]}, {BBOX[2]}] lon [{BBOX[1]}, {BBOX[3]}]")
    janela = f"a partir de {STOP_DATE.date()}" if START_DATE is None else f"[{STOP_DATE.date()}, {START_DATE.date()}]"
    log.info(f"Período de coleta    : {janela}")
    log.info(f"Contas configuradas  : {len(INSTALOADER_ACCOUNTS)} ({', '.join(INSTALOADER_ACCOUNTS) or '-'})")
    if COLLECT_WINDOW_START is not None:
        dias = ",".join(_WEEKDAY_LABELS[d] for d in sorted(COLLECT_WINDOW_DAYS))
        log.info(
            f"Janela de coleta     : {COLLECT_WINDOW_START:%H:%M}-{COLLECT_WINDOW_END:%H:%M} "
            f"({COLLECT_WINDOW_TZ}), dias={dias}"
        )
    else:
        log.info("Janela de coleta     : sem restrição de horário")

    conn = get_conn()

    L = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        save_metadata=False,
        quiet=True,
        request_timeout=30,
    )

    rotator = None
    if INSTALOADER_ACCOUNTS:
        rotator = AccountRotator(INSTALOADER_ACCOUNTS)
        if not rotator.ensure_active(L):
            rotator = None
    else:
        log.warning(
            "Nenhuma conta configurada (INSTALOADER_ACCOUNTS/INSTALOADER_USERNAME) — "
            "continuando sem login (rate limit mais agressivo)."
        )

    wait_for_window()

    # ── Fase 0: varredura geo_grid isolada (sem coleta de posts) ──
    if COLLECT_MODE == "geo_grid_scan":
        log.info("=== Varredura geo_grid (somente descoberta de locations) ===")
        if LOCATION_RESOLVE_MODE != "geo_grid":
            raise ValueError(
                "COLLECT_MODE=geo_grid_scan requer LOCATION_RESOLVE_MODE=geo_grid"
            )
        new_locations = resolve_location_ids_geo_grid(L, conn=conn, rotator=rotator)
        insert_locations(conn, new_locations)
        log.info(
            f"Varredura concluída — {len(new_locations)} locations novas. "
            "Use run-export.ps1/.sh com a query geo_grid_locations_lista para revisar."
        )
        conn.close()
        return

    # ── Fase 1: locations ─────────────────────────────────────
    osm_locations = []
    if COLLECT_MODE in ("both", "location"):
        log.info("=== Fase 1: coleta por locations ===")

        if LOCATION_RESOLVE_MODE == "geo_grid":
            log.info("Modo: geo_grid (grade de coordenadas via location_search)")
            new_locations = resolve_location_ids_geo_grid(L, conn=conn, rotator=rotator)
            insert_locations(conn, new_locations)
        else:
            log.info("Modo: osm_name (nome OSM → fbsearch/places)")
            osm_locations = fetch_osm_locations()
            ig_locations  = resolve_location_ids(L, osm_locations, conn=conn, rotator=rotator)
            insert_locations(conn, ig_locations)

        # Carrega só as locations cujos posts ainda não foram coletados —
        # uma reexecução após crash/interrupção retoma pelas pendentes,
        # sem revisitar do zero as já processadas.
        pending_locations = load_uncollected_locations(conn)
        log.info(f"Usando {len(pending_locations)} locations pendentes (sem posts coletados ainda) para coleta de posts")
        collect_posts(L, conn, pending_locations, rotator=rotator)
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
        collect_posts_by_hashtag(L, conn, hashtags, rotator=rotator)
    else:
        log.info("=== Fase 2 ignorada (COLLECT_MODE=location) ===")

    conn.close()
    log.info("Coleta finalizada.")


if __name__ == "__main__":
    main()
