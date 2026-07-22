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


def load_scanned_grid_points(conn, step_km: float) -> set[tuple[float, float]]:
    """Carrega os pontos da grade geo_grid já escaneados para um step_km."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT lat, lon FROM ig_geo_grid_scanned WHERE step_km = %s",
            (step_km,),
        )
        return {(row[0], row[1]) for row in cur.fetchall()}


def mark_grid_point_scanned(conn, lat: float, lon: float, step_km: float, venues_found: int):
    """Marca um ponto da grade como escaneado (cache para próximas rodadas)."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO ig_geo_grid_scanned (lat, lon, step_km, venues_found)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (lat, lon, step_km) DO UPDATE
                SET venues_found = EXCLUDED.venues_found,
                    scanned_at   = now()
        """, (lat, lon, step_km, venues_found))
    conn.commit()


def load_all_locations(conn) -> list[dict]:
    """Carrega todas as locations já conhecidas no banco (cache completo)."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT ig_location_id, name, ig_lat, ig_lon, osm_lat, osm_lon, osm_name
            FROM ig_locations
        """)
        return [
            {
                "id":       str(row[0]),
                "name":     row[1],
                "ig_lat":   row[2],
                "ig_lon":   row[3],
                "osm_lat":  row[4],
                "osm_lon":  row[5],
                "osm_name": row[6],
            }
            for row in cur.fetchall()
        ]


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
