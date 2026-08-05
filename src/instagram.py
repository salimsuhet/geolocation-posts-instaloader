import logging
import random
import requests
import time
import uuid
from collections import namedtuple
from datetime import datetime, timezone

import instaloader
from instaloader.exceptions import TooManyRequestsException

from .config import BATCH_SIZE, BBOX, STOP_DATE, START_DATE, IG_COOKIE, GEO_GRID_STEP_KM, GEO_GRID_ENDPOINT_MODE, T_MIN_SEARCH, T_MAX_SEARCH, T_MIN_POST, T_MAX_POST
from .db import insert_geolocations, insert_posts, load_scanned_grid_points, mark_grid_point_scanned, mark_location_collected
from .geo import all_geo_methods, GeoResult

log = logging.getLogger(__name__)


def sleep():
    """Pausa aleatória entre T_MIN_POST e T_MAX_POST (configurável no .env)."""
    time.sleep(random.uniform(T_MIN_POST, T_MAX_POST))


def sleep_search():
    """Pausa aleatória entre T_MIN_SEARCH e T_MAX_SEARCH (configurável no .env)."""
    time.sleep(random.uniform(T_MIN_SEARCH, T_MAX_SEARCH))


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


def _load_cached_locations(conn) -> dict[str, dict]:
    """Carrega locations já resolvidas do banco, indexadas por osm_name."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT osm_name, ig_location_id, name, ig_lat, ig_lon, osm_lat, osm_lon
            FROM ig_locations
            WHERE osm_name IS NOT NULL
        """)
        return {
            row[0]: {
                "id":       str(row[1]),
                "name":     row[2],
                "ig_lat":   row[3],
                "ig_lon":   row[4],
                "osm_lat":  row[5],
                "osm_lon":  row[6],
                "osm_name": row[0],
            }
            for row in cur.fetchall()
        }


def resolve_location_ids(L, osm_locations: list[dict], conn=None) -> list[dict]:
    """
    Para cada POI OSM, busca a IG location correspondente via fbsearch/places.
    Usa cache do banco para não repetir buscas já realizadas.
    """
    # Carrega cache do banco se conexão disponível
    cached = _load_cached_locations(conn) if conn else {}
    if cached:
        log.info(f"Cache: {len(cached)} locations já resolvidas no banco")

    # Separa o que já está em cache do que precisa ser buscado
    resolved   = [v for k, v in cached.items()]
    to_resolve = [loc for loc in osm_locations if loc["name"] not in cached]

    if not to_resolve:
        log.info("Todos os location IDs já estão em cache — pulando busca")
        return resolved

    log.info(f"{len(to_resolve)} locations novas para resolver ({len(cached)} já em cache)")

    total = len(to_resolve)
    sess = L.context._session  # sessão interna do instaloader com todos os headers corretos

    for i, loc in enumerate(to_resolve, start=1):
        if i == 1 or i % 50 == 0 or i == total:
            log.info(f"Resolvendo location IDs: {i}/{total} ({100*i//total}%)")
        try:
            r = sess.get(
                "https://i.instagram.com/api/v1/fbsearch/places/",
                params={"query": loc["name"], "count": 1},
                timeout=30,
            )

            if r.status_code == 400:
                data = r.json()
                if data.get("spam") or data.get("feedback_required"):
                    log.warning("Instagram sinalizou spam/rate-limit — acionando backoff")
                    backoff()
                    sleep_search()
                    continue

            r.raise_for_status()
            data = r.json()

            items = data.get("items", [])
            if items:
                place = items[0]["location"]
                entry = {
                    "id":       place["pk"],
                    "name":     place["name"],
                    "ig_lat":   place.get("lat"),
                    "ig_lon":   place.get("lng"),
                    "osm_lat":  loc["lat"],
                    "osm_lon":  loc["lon"],
                    "osm_name": loc["name"],
                }
                resolved.append(entry)

                if conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO ig_locations
                                (ig_location_id, name, ig_lat, ig_lon, osm_lat, osm_lon, osm_name)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (ig_location_id) DO UPDATE
                                SET osm_name = EXCLUDED.osm_name,
                                    resolved_at = now()
                        """, (
                            place["pk"], place["name"],
                            place.get("lat"), place.get("lng"),
                            loc["lat"], loc["lon"], loc["name"],
                        ))
                    conn.commit()

        except requests.exceptions.HTTPError as e:
            msg = str(e)
            log.warning(f"Erro resolvendo '{loc['name']}': {e}")
            if "401" in msg or "429" in msg:
                backoff()
        except requests.exceptions.Timeout:
            log.warning(f"Timeout resolvendo '{loc['name']}' — continuando")
        except Exception as e:
            log.warning(f"Erro resolvendo '{loc['name']}': {e}")

        sleep_search()  # sempre aguarda, independente de erro ou sucesso

    log.info(f"{len(resolved)} location_ids resolvidos no total")
    return resolved


def _geo_grid_points(bbox: tuple, step_km: float) -> list[tuple[float, float]]:
    """
    Gera grade de pontos (lat, lon) sobre o bounding box com espaçamento em km.
    1 grau de latitude ≈ 111 km; 1 grau de longitude ≈ 111 * cos(lat) km.
    """
    import math
    lat_min, lon_min, lat_max, lon_max = bbox
    lat_step = step_km / 111.0
    mid_lat   = (lat_min + lat_max) / 2
    lon_step  = step_km / (111.0 * math.cos(math.radians(mid_lat)))

    points = []
    lat = lat_min
    while lat <= lat_max:
        lon = lon_min
        while lon <= lon_max:
            points.append((round(lat, 6), round(lon, 6)))
            lon += lon_step
        lat += lat_step
    return points


def _location_search_mobile(lat: float, lon: float, cookie: str) -> requests.Response:
    """Endpoint da API mobile — costuma ser mais resiliente por conta."""
    return requests.get(
        "https://i.instagram.com/api/v1/location_search/",
        params={"latitude": lat, "longitude": lon},
        headers={
            "Cookie": cookie,
            "User-Agent": "Instagram 76.0.0.15.395 Android",
            "X-IG-App-ID": "936619743392459",
            "Accept": "*/*",
        },
        timeout=10,
    )


def _location_search_web(lat: float, lon: float, cookie: str) -> requests.Response:
    """Endpoint web original (técnica do Bellingcat) — algumas contas têm
    esse endpoint especificamente restrito mesmo com cookie válido."""
    return requests.get(
        "https://www.instagram.com/location_search/",
        params={"latitude": lat, "longitude": lon, "__a": 1},
        headers={"Cookie": cookie},
        timeout=10,
    )


_LOCATION_SEARCH_FETCHERS = {
    "mobile": _location_search_mobile,
    "web": _location_search_web,
}


def _parse_location_search_response(r: requests.Response) -> tuple[bool, list[dict], str]:
    """Interpreta a resposta de um dos endpoints location_search."""
    if r.status_code != 200:
        return False, [], f"HTTP {r.status_code}"

    try:
        data = r.json()
    except ValueError:
        # Instagram devolveu 200 com HTML em vez de JSON — geralmente
        # sinal de cookie expirado, conta sinalizada, ou esse endpoint
        # específico restrito para essa conta.
        body_lower = r.text.lower()
        if any(marker in body_lower for marker in ("login", "checkpoint", "challenge")):
            return False, [], "IG_COOKIE expirado, conta sinalizada, ou endpoint restrito para essa conta (Instagram devolveu página de login/checkpoint em vez de JSON)"
        return False, [], "resposta não é JSON válido"

    return True, data.get("venues", []), ""


def _fetch_locations_at_point(lat: float, lon: float, cookie: str) -> tuple[bool, list[dict], str]:
    """
    Chama o(s) endpoint(s) location_search do Instagram para um ponto
    específico, conforme GEO_GRID_ENDPOINT_MODE (mobile | web | both).
    Retorna (sucesso, venues, motivo). sucesso=False indica que o ponto não
    deve ser marcado como escaneado, para ser tentado de novo na próxima
    rodada. motivo é uma descrição curta da última falha (vazio quando
    sucesso).

    Em "both", tenta mobile primeiro e só tenta web se mobile falhar —
    algumas contas têm um dos dois endpoints bloqueado/restrito mesmo com
    cookie válido, então tentar o outro dá uma segunda chance ao ponto
    antes de desistir dele.
    """
    order = ("mobile", "web") if GEO_GRID_ENDPOINT_MODE == "both" else (GEO_GRID_ENDPOINT_MODE,)

    last_reason = ""
    for name in order:
        try:
            r = _LOCATION_SEARCH_FETCHERS[name](lat, lon, cookie)
        except requests.exceptions.RequestException as e:
            last_reason = f"[{name}] erro de rede: {e}"
            continue
        except Exception as e:
            last_reason = f"[{name}] erro inesperado: {e}"
            continue

        success, venues, reason = _parse_location_search_response(r)
        if success:
            return True, venues, ""
        last_reason = f"[{name}] {reason}"

    return False, [], last_reason


def resolve_location_ids_geo_grid(conn=None) -> list[dict]:
    """
    Descobre locations do Instagram varrendo uma grade de coordenadas sobre
    o bounding box configurado — abordagem do Bellingcat instagram-location-search.

    Não depende do OSM nem de busca por nome. Requer IG_COOKIE no .env.
    Usa cache do banco: pontos já cobertos não são repetidos.
    """
    if not IG_COOKIE:
        raise ValueError(
            "IG_COOKIE não definido no .env. "
            "Necessário para LOCATION_RESOLVE_MODE=geo_grid. "
            "Obtenha em: DevTools → Network → qualquer request do Instagram "
            "→ Request Headers → cookie"
        )

    # Carrega IDs já conhecidos para deduplicar
    known_ids: set[str] = set()
    if conn:
        with conn.cursor() as cur:
            cur.execute("SELECT ig_location_id FROM ig_locations")
            known_ids = {str(row[0]) for row in cur.fetchall()}
    if known_ids:
        log.info(f"Cache geo_grid: {len(known_ids)} locations já no banco")

    points = _geo_grid_points(BBOX, GEO_GRID_STEP_KM)
    total  = len(points)

    # Cache de pontos já escaneados (por step_km) — pula o que já foi feito
    scanned_points = load_scanned_grid_points(conn, GEO_GRID_STEP_KM) if conn else set()
    pending = [p for p in points if p not in scanned_points]

    log.info(
        f"Grade geo_grid: {total} pontos totais ({GEO_GRID_STEP_KM} km), "
        f"{len(scanned_points)} já escaneados, {len(pending)} pendentes"
    )

    if not pending:
        log.info("Grade geo_grid totalmente em cache — nenhuma consulta necessária")
        return []

    resolved: list[dict] = []
    new_count = 0
    pending_total = len(pending)

    for i, (lat, lon) in enumerate(pending, start=1):
        if i == 1 or i % 100 == 0 or i == pending_total:
            log.info(f"geo_grid: {i}/{pending_total} pontos pendentes | {new_count} locations novas")

        success, venues, fail_reason = _fetch_locations_at_point(lat, lon, IG_COOKIE)

        for v in venues:
            ext_id = str(v.get("external_id", ""))
            if not ext_id or ext_id in known_ids:
                continue

            entry = {
                "id":       ext_id,
                "name":     v.get("name", ""),
                "ig_lat":   v.get("lat"),
                "ig_lon":   v.get("lng"),
                "osm_lat":  None,
                "osm_lon":  None,
                "osm_name": None,
            }
            resolved.append(entry)
            known_ids.add(ext_id)
            new_count += 1

            if conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO ig_locations
                            (ig_location_id, name, ig_lat, ig_lon)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (ig_location_id) DO NOTHING
                    """, (ext_id, v.get("name", ""), v.get("lat"), v.get("lng")))
                conn.commit()

        if conn:
            if success:
                mark_grid_point_scanned(conn, lat, lon, GEO_GRID_STEP_KM, len(venues))
            else:
                log.warning(f"Falha ao consultar ({lat}, {lon}): {fail_reason} — será tentado de novo na próxima rodada")

        # pausa configurável entre pontos (mesmo intervalo do osm_name)
        sleep_search()

    log.info(f"geo_grid concluído: {new_count} locations novas descobertas, {pending_total} pontos escaneados")
    return resolved


def _geo_for_hashtag_post(post) -> list[GeoResult]:
    """
    Posts coletados por hashtag não têm ig_loc do OSM.
    Aplica apenas os métodos disponíveis sem osm_match/location_centroid.
    """
    return all_geo_methods(post, ig_loc={})


_MobileLocation = namedtuple("_MobileLocation", ["lat", "lng"])


class _MobilePost:
    """
    Post minimalista construído a partir do media retornado pela API
    mobile (i.instagram.com/api/v1/locations/{id}/sections/) — expõe só
    os atributos usados por collect_posts/all_geo_methods (shortcode,
    date_utc, owner_username, caption, location).

    Não usamos instaloader.Post aqui: seus internals (_field/_full_metadata)
    esperam o payload do endpoint web antigo (explore/locations/.../__a=1),
    que parou de funcionar para essa conta — e quebram com esse payload novo.
    """

    def __init__(self, media: dict):
        self.shortcode = media.get("code")
        self.date_utc = datetime.fromtimestamp(media["taken_at"], tz=timezone.utc)
        user = media.get("user") or {}
        self.owner_username = user.get("username")
        caption_data = media.get("caption")
        self.caption = caption_data.get("text") if caption_data else None
        loc = media.get("location") or {}
        self.location = _MobileLocation(loc.get("lat"), loc.get("lng"))


def _location_posts_mobile(session: requests.Session, location_id: str):
    """
    Itera os posts marcados numa location via API mobile do app
    (i.instagram.com/api/v1/locations/{id}/sections/, tab=recent) —
    mostra posts de qualquer usuário que marcou o local, igual à aba
    "Posts" ao tocar numa location tag no app, não o feed do dono/página.

    Substitui instaloader.Post.get_posts_by_location: o endpoint web
    equivalente (explore/locations/.../__a=1) parou de responder com JSON
    para essa conta (ver README). Pagina via o cursor `next_max_id` da
    própria resposta — `next_page`/`next_media_ids` não são cursores reais
    nesse endpoint (ficam vazios/estáticos).
    """
    headers = {
        "User-Agent": "Instagram 76.0.0.15.395 Android",
        "X-IG-App-ID": "936619743392459",
        "Accept": "*/*",
    }
    session_id = str(uuid.uuid4())
    device_uuid = str(uuid.uuid4())
    data = {"tab": "recent", "session_id": session_id, "_uuid": device_uuid}

    while True:
        r = session.post(
            f"https://i.instagram.com/api/v1/locations/{location_id}/sections/",
            headers=headers, data=data, timeout=15,
        )
        if r.status_code == 429:
            raise TooManyRequestsException(f"HTTP 429 em locations/{location_id}/sections/")
        r.raise_for_status()
        payload = r.json()

        for section in payload.get("sections", []):
            for item in section.get("layout_content", {}).get("medias", []):
                media = item.get("media")
                if media:
                    yield _MobilePost(media)

        next_max_id = payload.get("next_max_id")
        if not payload.get("more_available") or not next_max_id:
            break

        data = {
            "tab": "recent", "session_id": session_id, "_uuid": device_uuid,
            "max_id": next_max_id,
        }


def collect_posts(L, conn, locations: list[dict]):
    """
    Coleta posts por location ID (fonte: OSM → Instagram).
    Marca cada location como concluída (posts_collected_at) só quando
    termina sem erro — uma reexecução após crash/interrupção retoma pelas
    locations ainda pendentes, sem revisitar as já processadas.
    """
    for ig_loc in locations:
        log.info(f"Coletando location '{ig_loc['name']}' (id={ig_loc['id']})")

        post_batch = []
        geo_batch  = []
        ok = True

        try:
            posts = _location_posts_mobile(L.context._session, str(ig_loc["id"]))

            for post in posts:
                post_date = post.date_utc
                if post_date.tzinfo is None:
                    post_date = post_date.replace(tzinfo=timezone.utc)
                if post_date < STOP_DATE:
                    log.info("  → Post anterior a STOP_DATE, encerrando location")
                    break

                if START_DATE is None or post_date <= START_DATE:
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
            ok = False
        except Exception as e:
            log.error(f"Erro em location {ig_loc['id']}: {e}")
            ok = False

        if post_batch:
            insert_posts(conn, post_batch)
            insert_geolocations(conn, geo_batch)
            log.info(f"  → {len(post_batch)} posts / {len(geo_batch)} geos inseridos (flush final)")

        if conn and ok:
            mark_location_collected(conn, ig_loc["id"])

        # garante uma pausa mínima por location mesmo quando ela não tem
        # posts (senão locations vazias em sequência não pausam nada, já
        # que o sleep() do laço acima só roda por post processado)
        sleep()


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

                if START_DATE is not None and post_date > START_DATE:
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
