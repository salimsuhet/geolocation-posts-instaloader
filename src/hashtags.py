import logging
import re
import unicodedata
from pathlib import Path

log = logging.getLogger(__name__)

# Caminho do arquivo de hashtags fixas (montado no container)
HASHTAGS_FILE = Path("/app/hashtags.txt")


def _normalize(text: str) -> str:
    """Remove acentos, pontuação e espaços; retorna minúsculas sem #."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_str = nfkd.encode("ASCII", "ignore").decode("ASCII")
    return re.sub(r"[^a-z0-9]", "", ascii_str.lower())


def load_fixed_hashtags() -> set[str]:
    """Lê hashtags do arquivo externo. Ignora comentários e linhas vazias."""
    if not HASHTAGS_FILE.exists():
        log.warning(f"Arquivo de hashtags não encontrado: {HASHTAGS_FILE}")
        return set()

    tags = set()
    for line in HASHTAGS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tags.add(_normalize(line))

    log.info(f"{len(tags)} hashtags fixas carregadas de {HASHTAGS_FILE}")
    return tags


def generate_from_poi_names(osm_locations: list[dict]) -> set[str]:
    """
    Gera hashtags a partir dos nomes dos POIs OSM.

    Estratégia:
      - Nome completo normalizado  → ex: "Praia de Camburi" → praiadecamburi
      - Última palavra (≥5 chars)  → ex: "Praia de Camburi" → camburi
      - Remove stopwords comuns para evitar hashtags genéricas
    """
    STOPWORDS = {
        "de", "da", "do", "das", "dos", "e", "em", "a", "o", "as", "os",
        "um", "uma", "para", "com", "sem", "por", "ponto", "rua", "avenida",
        "av", "praca", "largo", "travessa", "alameda", "rodovia", "br",
        "es", "n", "s", "l", "o",
    }

    tags = set()
    for loc in osm_locations:
        name = loc.get("name", "")
        if not name:
            continue

        # Nome completo
        full = _normalize(name)
        if len(full) >= 5:
            tags.add(full)

        # Palavras individuais com significado (≥5 chars, fora das stopwords)
        words = [_normalize(w) for w in name.split()]
        for word in words:
            if len(word) >= 5 and word not in STOPWORDS:
                tags.add(word)

    log.info(f"{len(tags)} hashtags geradas a partir de {len(osm_locations)} POIs")
    return tags


def build_hashtag_list(osm_locations: list[dict]) -> list[str]:
    """
    Combina hashtags fixas e geradas automaticamente.
    Retorna lista ordenada e deduplicada.
    """
    fixed     = load_fixed_hashtags()
    generated = generate_from_poi_names(osm_locations)
    combined  = sorted(fixed | generated)
    log.info(f"Total: {len(combined)} hashtags únicas ({len(fixed)} fixas + "
             f"{len(generated - fixed)} geradas exclusivamente dos POIs)")
    return combined
