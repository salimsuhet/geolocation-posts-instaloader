from dataclasses import dataclass
from typing import Optional

from .config import BBOX_CENTER_LAT, BBOX_CENTER_LON


@dataclass
class GeoResult:
    method: str
    confidence: int
    lat: Optional[float]
    lon: Optional[float]


def all_geo_methods(post, ig_loc: dict) -> list[GeoResult]:
    """
    Aplica todos os 4 métodos ao post e retorna uma lista de GeoResult.
    Métodos que não conseguem produzir coordenada retornam lat=None, lon=None.
    bbox_centroid é o único garantidamente disponível.
    """
    loc = post.location
    results = []

    # 1. post_latlon — coordenada direta no post
    if loc and _valid(loc.lat) and _valid(loc.lng):
        results.append(GeoResult("post_latlon", 95, float(loc.lat), float(loc.lng)))
    else:
        results.append(GeoResult("post_latlon", 95, None, None))

    # 2. location_centroid — centroide da IG location
    if _valid(ig_loc.get("ig_lat")) and _valid(ig_loc.get("ig_lon")):
        results.append(GeoResult("location_centroid", 70, float(ig_loc["ig_lat"]), float(ig_loc["ig_lon"])))
    else:
        results.append(GeoResult("location_centroid", 70, None, None))

    # 3. osm_match — ponto OSM que originou a location
    if _valid(ig_loc.get("osm_lat")) and _valid(ig_loc.get("osm_lon")):
        results.append(GeoResult("osm_match", 50, float(ig_loc["osm_lat"]), float(ig_loc["osm_lon"])))
    else:
        results.append(GeoResult("osm_match", 50, None, None))

    # 4. bbox_centroid — sempre disponível, confiança baixa
    results.append(GeoResult("bbox_centroid", 10, BBOX_CENTER_LAT, BBOX_CENTER_LON))

    return results


def _valid(v) -> bool:
    try:
        return v is not None and float(v) != 0.0
    except (TypeError, ValueError):
        return False
