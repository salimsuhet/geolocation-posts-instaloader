import logging
import random
import requests
import time
from datetime import timezone

import instaloader
from instaloader.exceptions import TooManyRequestsException

from .config import BASE_SLEEP, BASE_SLEEP_SEARCH, BATCH_SIZE, BBOX, STOP_DATE
from .db import insert_geolocations, insert_posts
from .geo import all_geo_methods, GeoResult

log = logging.getLogger(__name__)


def sleep():
    time.sleep(BASE_SLEEP * random.uniform(0.7, 1.5))


def sleep_search():
    """Pausa conservadora entre chamadas ao topsearch (mais sensível a bloqueio)."""
    time.sleep(BASE_SLEEP_SEARCH * random.uniform(0.8, 1.6))


def backoff():
    wait = random.randint(300, 900)
    log.warning(f"Rate limit atingido — aguardando {wait}s")
    time.sleep(wait)


def _within_bbox(post) -> bool:
    """Verifica se o post tem coordenada direta dentro do bounding box."""
    loc = post.location
    if not loc:
        return True  # sem coordenada: inclui (filtragem posterior via método geo)
    try:
        lat, lon = float(loc.lat), float(loc.lng)
        if lat == 0.0 and lon == 0.0:
            return True
        lat_min, lon_min, lat_max, lon_max = BBOX
        return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max
    except (TypeError, ValueError):
        return True


def resolve_location_ids(L, osm_locations: list[dict]) -> list[dict]:
    """
    Para cada POI OSM, busca a IG location correspondente via fbsearch/places.
    Preserva as coordenadas de ambas as fontes para uso nos métodos geo.
    """
    resolved = []
    total = len(osm_locations)
    cookies = L.context._session.cookies
    headers = {
        "User-Agent": "Instagram 275.0.0.27.98",
        "X-IG-App-ID": "936619743392459",
    }

    for i, loc in enumerate(osm_locations, start=1):
        if i == 1 or i % 50 == 0 or i == total:
            log.info(f"Resolvendo location IDs: {i}/{total} ({100*i//total}%)")
        try:
            r = requests.get(
                "https://i.instagram.com/api/v1/fbsearch/places/",
                params={"query": loc["name"], "count": 1},
                cookies=cookies,
                headers=headers,
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()

            items = data.get("items", [])
            if items:
                place = items[0]["location"]
                resolved.append({
                    "id":       place["pk"],
                    "name":     place["name"],
                    "ig_lat":   place.get("lat"),
                    "ig_lon":   place.get("lng"),
                    "osm_lat":  loc["lat"],
                    "osm_lon":  loc["lon"],
                    "osm_name": loc["name"],
                })

            sleep_search()

        except requests.exceptions.HTTPError as e:
            msg = str(e)
            log.warning(f"Erro resolvendo '{loc['name']}': {e}")
            if "401" in msg or "429" in msg:
                backoff()
        except requests.exceptions.Timeout:
            log.warning(f"Timeout resolvendo '{loc['name']}' — continuando")
        except Exception as e:
            log.warning(f"Erro resolvendo '{loc['name']}': {e}")

    log.info(f"{len(resolved)} location_ids resolvidos")
    return resolved

    log.info(f"{len(resolved)} location_ids resolvidos")
    return resolved


def _geo_for_hashtag_post(post) -> list[GeoResult]:
    """
    Posts coletados por hashtag não têm ig_loc do OSM.
    Aplica apenas os métodos disponíveis sem osm_match/location_centroid.
    """
    return all_geo_methods(post, ig_loc={})


def collect_posts(L, conn, locations: list[dict]):
    """Coleta posts por location ID (fonte: OSM → Instagram)."""
    for ig_loc in locations:
        log.info(f"Coletando location '{ig_loc['name']}' (id={ig_loc['id']})")

        post_batch = []
        geo_batch  = []

        try:
            posts = instaloader.Post.get_posts_by_location(L.context, ig_loc["id"])

            for post in posts:
                post_date = post.date_utc
                if post_date.tzinfo is None:
                    post_date = post_date.replace(tzinfo=timezone.utc)
                if post_date < STOP_DATE:
                    log.info("  → Post anterior a STOP_DATE, encerrando location")
                    break

                caption = (post.caption or "")[:280].replace("\n", " ") if post.caption else None

                post_batch.append({
                    "post_id":         post.shortcode,
                    "taken_at":        post.date_utc,
                    "ig_location_id":  ig_loc["id"],
                    "owner_username":  post.owner_username,
                    "caption_snippet": caption,
                })

                for geo in all_geo_methods(post, ig_loc):
                    geo_batch.append({
                        "post_id":    post.shortcode,
                        "method":     geo.method,
                        "lat":        geo.lat,
                        "lon":        geo.lon,
                        "confidence": geo.confidence,
                    })

                available = sum(1 for g in all_geo_methods(post, ig_loc) if g.lat is not None)
                log.debug(f"  ✓ {post.shortcode}: {available}/4 métodos com coordenada")

                if len(post_batch) >= BATCH_SIZE:
                    insert_posts(conn, post_batch)
                    insert_geolocations(conn, geo_batch)
                    log.info(f"  → {len(post_batch)} posts / {len(geo_batch)} geos inseridos")
                    post_batch = []
                    geo_batch  = []

                sleep()

        except TooManyRequestsException:
            backoff()
        except Exception as e:
            log.error(f"Erro em location {ig_loc['id']}: {e}")

        if post_batch:
            insert_posts(conn, post_batch)
            insert_geolocations(conn, geo_batch)
            log.info(f"  → {len(post_batch)} posts / {len(geo_batch)} geos inseridos (flush final)")


def collect_posts_by_hashtag(L, conn, hashtags: list[str]):
    """
    Coleta posts por hashtag. Posts sem location ficam com ig_location_id=NULL
    e recebem apenas os métodos geo disponíveis (post_latlon e bbox_centroid).
    Posts com coordenada fora do bounding box são descartados.
    """
    # ig_loc vazio: osm_match e location_centroid ficarão NULL
    empty_loc = {"ig_lat": None, "ig_lon": None, "osm_lat": None, "osm_lon": None}

    for tag in hashtags:
        log.info(f"Coletando hashtag #{tag}")

        post_batch = []
        geo_batch  = []
        skipped    = 0

        try:
            hashtag = instaloader.Hashtag.from_name(L.context, tag)
            iterator = hashtag.get_posts_resumable()

            for post in iterator:
                post_date = post.date_utc
                if post_date.tzinfo is None:
                    post_date = post_date.replace(tzinfo=timezone.utc)
                if post_date < STOP_DATE:
                    log.info(f"  → Post anterior a STOP_DATE, encerrando #{tag}")
                    break

                if not _within_bbox(post):
                    skipped += 1
                    continue

                caption = (post.caption or "")[:280].replace("\n", " ") if post.caption else None

                post_batch.append({
                    "post_id":         post.shortcode,
                    "taken_at":        post.date_utc,
                    "ig_location_id":  post.location.id if post.location else None,
                    "owner_username":  post.owner_username,
                    "caption_snippet": caption,
                })

                for geo in all_geo_methods(post, empty_loc):
                    geo_batch.append({
                        "post_id":    post.shortcode,
                        "method":     geo.method,
                        "lat":        geo.lat,
                        "lon":        geo.lon,
                        "confidence": geo.confidence,
                    })

                if len(post_batch) >= BATCH_SIZE:
                    insert_posts(conn, post_batch)
                    insert_geolocations(conn, geo_batch)
                    log.info(f"  → {len(post_batch)} posts inseridos (#{tag})")
                    post_batch = []
                    geo_batch  = []

                sleep()

        except TooManyRequestsException:
            backoff()
        except StopIteration:
            pass  # iterador esgotado normalmente
        except Exception as e:
            log.error(f"Erro na hashtag #{tag}: {e}")

        if post_batch:
            insert_posts(conn, post_batch)
            insert_geolocations(conn, geo_batch)
            log.info(f"  → {len(post_batch)} posts inseridos, flush final (#{tag})")

        if skipped:
            log.info(f"  → {skipped} posts descartados (fora do bounding box)")
