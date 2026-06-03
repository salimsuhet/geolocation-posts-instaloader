import logging
import subprocess
from pathlib import Path

import osmium
import requests

from .config import BBOX, OVERPASS_URL, OSM_PBF_PATH, OSM_PBF_FILTERED_PATH

log = logging.getLogger(__name__)

TAGS_DE_INTERESSE = {"tourism", "leisure", "amenity"}


class _POIHandler(osmium.SimpleHandler):
    """Extrai nós com name e tag de interesse dentro do bounding box."""

    def __init__(self, bbox):
        super().__init__()
        self.bbox = bbox   # (lat_min, lon_min, lat_max, lon_max)
        self.results: list[dict] = []
        self._seen: set[str] = set()

    def node(self, n):
        lat, lon = float(n.location.lat), float(n.location.lon)
        lat_min, lon_min, lat_max, lon_max = self.bbox

        if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
            return

        tags = {t.k: t.v for t in n.tags}
        name = tags.get("name")
        if not name:
            return
        if not any(k in tags for k in TAGS_DE_INTERESSE):
            return

        key = name.lower().strip()
        if key in self._seen:
            return
        self._seen.add(key)
        self.results.append({"name": name, "lat": lat, "lon": lon})


def _ensure_filtered_pbf() -> None:
    """Gera o arquivo .filtered.pbf recortado pelo BBOX, se ainda não existir."""
    if Path(OSM_PBF_FILTERED_PATH).exists():
        log.info(f"PBF filtrado já existe: {OSM_PBF_FILTERED_PATH}")
        return
    lat_min, lon_min, lat_max, lon_max = BBOX
    # osmium extract usa ordem lon_min,lat_min,lon_max,lat_max
    bbox_str = f"{lon_min},{lat_min},{lon_max},{lat_max}"
    log.info(f"Gerando PBF filtrado via osmium extract → {OSM_PBF_FILTERED_PATH}")
    subprocess.run(
        [
            "osmium", "extract",
            "--bbox", bbox_str,
            OSM_PBF_PATH,
            "-o", OSM_PBF_FILTERED_PATH,
            "--overwrite",
        ],
        check=True,
    )
    log.info("PBF filtrado gerado com sucesso.")


def _fetch_from_pbf() -> list[dict]:
    """Lê POIs diretamente do arquivo .pbf local (filtrado pelo BBOX)."""
    _ensure_filtered_pbf()
    log.info(f"Lendo POIs do arquivo filtrado: {OSM_PBF_FILTERED_PATH}")
    handler = _POIHandler(BBOX)
    handler.apply_file(OSM_PBF_FILTERED_PATH, locations=True)
    log.info(f"{len(handler.results)} locais OSM extraídos do .pbf")
    return handler.results


def _fetch_from_overpass() -> list[dict]:
    """Fallback: busca POIs via Overpass API."""
    log.info("Arquivo .pbf não encontrado — usando Overpass API (mais lento)")
    query = f"""
    [out:json][timeout:120];
    (
      node["tourism"]["name"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
      node["leisure"]["name"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
      node["amenity"]["name"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
    );
    out body;
    """
    r = requests.post(OVERPASS_URL, data={"data": query}, timeout=150,
                      headers={"User-Agent": "instagram-geolocation-collector/1.0"})
    r.raise_for_status()
    data = r.json()

    seen: set[str] = set()
    results = []
    for el in data["elements"]:
        name = el.get("tags", {}).get("name")
        if not name:
            continue
        key = name.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        results.append({"name": name, "lat": el["lat"], "lon": el["lon"]})

    log.info(f"{len(results)} locais OSM coletados via Overpass")
    return results


def fetch_osm_locations() -> list[dict]:
    """
    Retorna POIs dentro do bounding box.
    Usa o arquivo .pbf local se disponível; caso contrário, cai no Overpass.
    """
    if Path(OSM_PBF_PATH).exists():
        return _fetch_from_pbf()
    return _fetch_from_overpass()
