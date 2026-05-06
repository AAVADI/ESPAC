from __future__ import annotations

import re
import unicodedata
from typing import Iterable

GROUPS = {
    "cereals",
    "forages_pastures",
    "fruits",
    "industrial_cash",
    "pulses_oilseeds",
    "roots_tubers",
    "vegetables",
}


def normalize_crop_name(value: str) -> str:
    txt = unicodedata.normalize("NFKD", str(value or "").upper())
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def _token_variants(token: str) -> set[str]:
    out = {normalize_crop_name(token)}
    base = re.sub(r"\s*\([^)]*\)", "", token)
    out.add(normalize_crop_name(base))
    if "/" in token:
        for part in token.split("/"):
            out.add(normalize_crop_name(part))
    return {x for x in out if x}


def _build_curated_map() -> dict[str, str]:
    curated: dict[str, str] = {}

    groups: dict[str, list[str]] = {
        "cereals": [
            "ARROZ",
            "ARROZ (EN CASCARA)",
            "AVENA",
            "CEBADA",
            "MAIZ DURO CHOCLO (CHOCLO)",
            "MAIZ DURO SECO (GRANO SECO)",
            "MAIZ DURO SECO (MAZORCA)",
            "MAIZ SUAVE CHOCLO (CHOCLO)",
            "MAIZ SUAVE SECO (GRANO SECO)",
            "MAIZ SUAVE SECO (MAZORCA)",
            "QUINUA",
            "TRIGO",
            "CENTENO",
        ],
        "forages_pastures": [
            "BRACHIARIA",
            "GRAMALOTE",
            "PASTO MIEL (CHILENA)",
            "SABOYA",
            "ALFALFA",
            "CAÑA FORRAJERA",
            "DALIS",
            "JANEIRO",
            "KIKUYO",
            "MARANDU",
            "MERKERON",
            "MICAY",
            "OTROS PASTOS CULTIVADOS",
            "PASTO AZUL",
            "PASTO ELEFANTE",
            "PASTO GUINEA",
            "RAIGRAS",
            "SETARIA ESPLENDIDA",
            "SETARIA ESPLENDIDA",
            "TREBOL BLANCO",
            "TREBOL ROJO",
            "YARAGUA",
            "PASTO MIXTO",
            "OTROS FORRAJES",
            "VICIA FORRAJERA",
            "LENTEJA FORRAJERA",
            "CEBADA FORRAJERA",
            "AVENA FORRAJERA",
            "MAIZ FORRAJERO",
            "CENTENO FORRAJERO",
        ],
        "fruits": [
            "AGUACATE",
            "AGUACATE (FRUTA FRESCA)",
            "BANANO DE EXPORTACION",
            "BANANO (FRUTA FRESCA)",
            "CHIRIMOYA",
            "LIMON",
            "LIMON (FRUTA FRESCA)",
            "LIMÓN",
            "MANDARINA",
            "MANGO",
            "MANGO (FRUTA FRESCA)",
            "MANZANA",
            "MARACUYA",
            "MARACUYA (FRUTA FRESCA)",
            "MARACUYÁ",
            "NARANJA",
            "NARANJA (FRUTA FRESCA)",
            "ORITO",
            "ORITO (FRUTA FRESCA)",
            "OTROS BANANOS",
            "PAPAYA",
            "PERA",
            "PIÑA",
            "PIÑA (FRUTA FRESCA)",
            "PLATANO",
            "PLATANO (FRUTA FRESCA)",
            "PLÁTANO",
            "TOMATE DE ARBOL",
            "TOMATE DE ARBOL (FRUTA FRESCA)",
            "TOMATE DE ÁRBOL",
            "UVA (VID)",
            "MORA",
            "PITAHAYA",
            "ARAZA",
            "ARÁNDANO",
            "BABACO",
            "BADEA",
            "BOROJO",
            "CAIMITO",
            "CAPULI",
            "CEREZA",
            "CIRUELO",
            "CLAUDIA",
            "COCO (COCOTERO)",
            "DURAZNO (MELOCOTON)",
            "FRUTILLAS O FRESAS",
            "GRANADILLA",
            "GUABA",
            "GUANABANA",
            "GUAYABA",
            "HIGO",
            "HUERTO FRUTAL",
            "LIMA",
            "MAMEY",
            "MELON",
            "MENBRILLO",
            "NARANJILLA",
            "NISPERO",
            "PITAHAYA AMARILLA",
            "PITAHAYA ROJA",
            "SANDIA",
            "TAMARINDO",
            "TAXO",
            "TOMATILLO",
            "TORONJA",
            "TUNA",
            "UVILLA",
            "ZAPOTE",
        ],
        "industrial_cash": [
            "CACAO CCN51 O RAMILLA (ALMENDRA FRESCA)",
            "CACAO CCN51 O RAMILLA (ALMENDRA SECA)",
            "CACAO (ALMENDRA SECA)",
            "CACAO FINO DE AROMA (ALMENDRA FRESCA)",
            "CACAO FINO DE AROMA (ALMENDRA SECA)",
            "CAFE (GRANO ORO)",
            "CAFÉ ARABIGO (CEREZA FRESCA O MADURA)",
            "CAFÉ ARABIGO (CEREZA O BOLA SECA)",
            "CAFÉ ARABIGO (GRANO ORO)",
            "CAFÉ ARABIGO (PERGAMINO OREADO)",
            "CAFÉ ARABIGO (PERGAMINO SECO)",
            "CAFÉ ROBUSTA (CEREZA FRESCA O MADURA)",
            "CAFÉ ROBUSTA (CEREZA O BOLA SECA)",
            "CAFÉ ROBUSTA (GRANO ORO)",
            "CAFÉ ROBUSTA (PERGAMINO OREADO)",
            "CAFÉ ROBUSTA (PERGAMINO SECO)",
            "CAÑA DE AZÚCAR / AZÚCAR",
            "CANA DE AZUCAR / AZUCAR (TALLO FRESCO)",
            "CAÑA DE AZÚCAR / OTROS USOS",
            "CANA DE AZUCAR / OTROS USOS (TALLO FRESCO)",
            "CAÑA DE AZÚCAR /BIOCOMBUSTIBLE",
            "PALMA AFRICANA",
            "PALMA AFRICANA (FRUTA FRESCA)",
            "PALMITO",
            "PALMITO (TALLO FRESCO)",
            "TABACO",
            "ABACÁ",
            "BAMBÚ O CAÑA GUADUA",
            "CABUYA",
            "CAUCHO",
            "CEIBO",
            "PAJA TOQUILLA",
            "TÉ",
        ],
        "pulses_oilseeds": [
            "AJONJOLI",
            "ARVEJA SECA (GRANO SECO)",
            "ARVEJA SECA (VAINA SECA)",
            "ARVEJA TIERNA (GRANO TIERNO)",
            "ARVEJA TIERNA (VAINA)",
            "FREJOL SECO (GRANO SECO)",
            "FREJOL SECO (VAINA SECA)",
            "FREJOL TIERNO (GRANO TIERNO)",
            "FREJOL TIERNO (VAINA)",
            "HABA SECA (GRANO SECO)",
            "HABA SECA (VAINA SECA)",
            "HABA TIERNA (GRANO TIERNO)",
            "HABA TIERNA (VAINA)",
            "MANI",
            "SOYA",
            "CHOCHO",
            "LENTEJA",
        ],
        "roots_tubers": [
            "CAMOTE",
            "OCA",
            "PAPA",
            "PAPA CHINA, PELMA",
            "YUCA",
            "JICAMA",
            "JÍCAMA",
            "MALANGA",
            "MASHUA",
            "MELLOCO",
        ],
        "vegetables": [
            "AJO",
            "BROCOLI",
            "CEBOLLA BLANCA",
            "CEBOLLA COLORADA",
            "CEBOLLA PERLA",
            "COL",
            "COLIFLOR",
            "ESPINACA",
            "HUERTO HORTICOLA",
            "LECHUGA",
            "PEPINO DULCE",
            "PIMIENTO",
            "TOMATE RIÑON",
            "ZANAHORIA AMARILLA",
            "ZANAHORIA BLANCA",
            "ACHIOTE",
            "ACELGA",
            "AJI",
            "ALCACHOFA",
            "APIO",
            "CARDAMOMO",
            "CILANTRO",
            "ESPARRAGO",
            "NABO",
            "PEPINILLO",
            "PEREJIL",
            "PIMIENTA NEGRA (GRANO FRESCO)",
            "PIMIENTA NEGRA (GRANO SECO)",
            "PLANTAS MEDICINALES",
            "RABANO",
            "REMOLACHA",
            "ROMANESCO",
            "SABILA",
            "SACHA INCHI",
            "SUQUINI (ZUCHINI)",
            "VAINITA",
            "ZAMBO",
            "ZAPALLO (CALABAZA)",
        ],
    }

    for group, crops in groups.items():
        for crop in crops:
            for variant in _token_variants(crop):
                curated[variant] = group

    return curated


CURATED_CROP_TO_GROUP = _build_curated_map()


def infer_crop_group_row(crop_name: str, category: str = "", packaging_type2: str = "") -> str:
    name = normalize_crop_name(crop_name)
    if not name:
        return "(unknown)"

    direct = CURATED_CROP_TO_GROUP.get(name)
    if direct:
        return direct

    # Only the four explicitly-authorized exceptions can use rule-based routing.
    if name == "OTROS PERMANENTES":
        return "fruits"

    if name == "OTROS TRANSITORIOS":
        p2 = normalize_crop_name(packaging_type2)
        if "FRUTA" in p2:
            return "fruits"
        if "TUBERCULO" in p2 or "RAIZ" in p2:
            return "roots_tubers"
        if "BULBO" in p2 or "REPOLLO" in p2 or "HORTALIZA" in p2 or "VAINA" in p2:
            return "vegetables"
        if "GRANO" in p2:
            return "pulses_oilseeds"
        return "vegetables"

    if name == "VIVEROS DE PERMANENTES":
        return "fruits"

    if name == "VIVEROS TRANSITORIOS":
        return "vegetables"

    return "other"


def canonical_crop_group_token(group_name: str) -> str:
    g = str(group_name or "").strip().lower()
    if not g:
        return ""
    g = re.sub(r"_(permanent|transitory)$", "", g)
    return g


def find_unmapped_crops(crop_names: Iterable[str]) -> list[str]:
    unknown: set[str] = set()
    for crop in crop_names:
        raw = str(crop or "").strip()
        if not raw:
            continue
        group = infer_crop_group_row(raw)
        if group == "other":
            unknown.add(normalize_crop_name(raw))
    return sorted(unknown)
