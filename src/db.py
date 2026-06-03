import psycopg2
from psycopg2.extras import execute_values

from .config import DB_CONFIG


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def insert_locations(conn, rows: list[dict]):
    sql = """
        INSERT INTO ig_locations
            (ig_location_id, name, ig_lat, ig_lon, osm_lat, osm_lon, osm_name)
        VALUES %s
        ON CONFLICT (ig_location_id) DO NOTHING;
    """
    values = [
        (
            r["id"],
            r["name"],
            r.get("ig_lat"),
            r.get("ig_lon"),
            r.get("osm_lat"),
            r.get("osm_lon"),
            r.get("osm_name"),
        )
        for r in rows
    ]
    with conn.cursor() as cur:
        execute_values(cur, sql, values)
    conn.commit()


def insert_posts(conn, rows: list[dict]):
    """Insere metadados do post (sem geo)."""
    sql = """
        INSERT INTO ig_posts
            (post_id, taken_at, ig_location_id, owner_username,
             caption_snippet, source, source_value)
        VALUES %s
        ON CONFLICT (post_id) DO NOTHING;
    """
    values = [
        (
            r["post_id"],
            r["taken_at"],
            r.get("ig_location_id"),
            r.get("owner_username"),
            r.get("caption_snippet"),
            r.get("source", "location"),
            r.get("source_value"),
        )
        for r in rows
    ]
    with conn.cursor() as cur:
        execute_values(cur, sql, values)
    conn.commit()


def insert_geolocations(conn, rows: list[dict]):
    """
    Insere uma linha por (post_id, method).
    lat/lon pode ser NULL quando o método não produz coordenada.
    """
    sql = """
        INSERT INTO ig_post_geolocations
            (post_id, method, lat, lon, confidence)
        VALUES %s
        ON CONFLICT (post_id, method) DO NOTHING;
    """
    values = [
        (
            r["post_id"],
            r["method"],
            r["lat"],
            r["lon"],
            r["confidence"],
        )
        for r in rows
    ]
    with conn.cursor() as cur:
        execute_values(cur, sql, values)
    conn.commit()
