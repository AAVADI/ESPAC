from __future__ import annotations

import argparse
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
import re
from typing import Callable
import unicodedata

import pandas as pd


_CWD = Path.cwd()
if (_CWD / "inputs").exists() and (_CWD / "outputs").exists():
    PROJECT_DIR = _CWD
elif (_CWD.parent / "inputs").exists() and (_CWD.parent / "outputs").exists():
    PROJECT_DIR = _CWD.parent
else:
    PROJECT_DIR = _CWD

DEFAULT_ECOINVENT = PROJECT_DIR / "inputs/00_Database_Overview_ecoinvent_v3_12.xlsx"
DEFAULT_AGRIBALYSE_CONV = PROJECT_DIR / "inputs/00_AGRIBALYSE3_2_partie_agriculture_conv_PublieNOV25.xlsx"
DEFAULT_AGRIBALYSE_BIO = PROJECT_DIR / "inputs/00_AGRIBALYSE3_2_Tableur_agriculture_bio_PublieNov24.xlsx"
DEFAULT_AGRIBALYSE_ORGANIC_FERT = PROJECT_DIR / "inputs/00_agribalyse_organic_fertilizers.csv"
DEFAULT_EXCHANGES = PROJECT_DIR / "outputs/04_exchanges_table.xlsx"
DEFAULT_CATALOG_CSV = PROJECT_DIR / "inputs/04_lci_process_catalog.csv"
DEFAULT_MATCH_XLSX = PROJECT_DIR / "outputs/04_exchanges_table_with_process_matches.xlsx"
DEFAULT_TOP_N = 3


TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")


def norm_text(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)) or x is pd.NA:
        s = ""
    else:
        try:
            if pd.isna(x):
                s = ""
            else:
                s = str(x)
        except Exception:
            s = str(x)
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("&", " and ")
    s = re.sub(r"\s+", " ", s)
    return s


def norm_name(x) -> str:
    s = norm_text(x)
    # normalize ecospold/ecoinvent decorative punctuation but keep semantic tokens
    s = s.replace("|", " ")
    s = s.replace("{", " ").replace("}", " ")
    s = s.replace(",", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def tokenize_name(x) -> list[str]:
    s = norm_name(x)
    toks = [t for t in TOKEN_SPLIT_RE.split(s) if t]
    stop = {
        "market",
        "for",
        "at",
        "plant",
        "cut",
        "off",
        "u",
        "economic",
        "the",
        "and",
        "of",
        "in",
    }
    return [t for t in toks if t not in stop and len(t) > 1]


def parse_agribalyse_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    # Agribalyse public files have a 3-row banner/header structure; row index 2 holds usable column names.
    df = pd.read_excel(path, sheet_name=sheet_name, header=2)
    df = df.rename(columns={c: str(c).strip() for c in df.columns})
    if "LCI Name" not in df.columns:
        raise ValueError(f"'LCI Name' column not found in {path} / {sheet_name}")

    # First row after header often repeats units/labels; keep rows with an actual LCI name.
    out = pd.DataFrame(
        {
            "database": "Agribalyse",
            "database_variant": "conventional" if "conventionnel" in sheet_name.lower() else "organic",
            "source_sheet": sheet_name,
            "process_name": df["LCI Name"].astype(str).str.strip(),
            "location": pd.NA,
            "unit": "kg",  # table describes impacts for 1 kg product sortie ferme
            "reference_product": df.get("Nom du Produit en Français", pd.Series([pd.NA] * len(df))),
            "category": df.get("Catégorie", pd.Series([pd.NA] * len(df))),
            "extra_type": df.get("Type de production", pd.Series([pd.NA] * len(df))),
        }
    )
    out["reference_product"] = out["reference_product"].astype(str).replace({"nan": ""}).str.strip()
    out["category"] = out["category"].astype(str).replace({"nan": ""}).str.strip()
    out["extra_type"] = out["extra_type"].astype(str).replace({"nan": ""}).str.strip()
    out = out[out["process_name"].notna() & (out["process_name"].str.lower() != "nan")].copy()
    # Drop repeated unit/label rows and empties
    out = out[
        out["process_name"].str.strip().ne("")
        & ~out["process_name"].str.contains(r"^LCI Name$", case=False, na=False)
    ].copy()
    return out.reset_index(drop=True)


def build_agribalyse_catalog(conv_path: Path, bio_path: Path) -> pd.DataFrame:
    frames = []
    for p in [conv_path, bio_path]:
        xl = pd.ExcelFile(p)
        target_sheet = next((s for s in xl.sheet_names if s.lower().startswith("agb 3.2 agricole")), None)
        if not target_sheet:
            raise ValueError(f"No AGB sheet found in {p}")
        frames.append(parse_agribalyse_sheet(p, target_sheet))
    out = pd.concat(frames, ignore_index=True)
    out["catalog_source_file"] = out["database_variant"].map(
        {"conventional": conv_path.name, "organic": bio_path.name}
    )
    return out


def build_ecoinvent_catalog(path: Path, preferred_sheet: str = "Cut-Off AO") -> pd.DataFrame:
    xl = pd.ExcelFile(path)
    if preferred_sheet not in xl.sheet_names:
        # Fallback to any AO sheet with activity names
        ao = [s for s in xl.sheet_names if s.endswith("AO")]
        if not ao:
            raise ValueError(f"No AO sheet found in {path}")
        preferred_sheet = ao[0]

    df = xl.parse(preferred_sheet)
    df = df.rename(columns={c: str(c).strip() for c in df.columns})

    activity_col = "Activity Name" if "Activity Name" in df.columns else None
    product_col = "Reference Product Name" if "Reference Product Name" in df.columns else ("Product Name" if "Product Name" in df.columns else None)
    geography_col = "Geography" if "Geography" in df.columns else None
    unit_col = "Unit" if "Unit" in df.columns else None
    if not activity_col:
        raise ValueError(f"Activity Name not found in ecoinvent sheet {preferred_sheet}")

    out = pd.DataFrame(
        {
            "database": "ecoinvent",
            "database_variant": preferred_sheet,
            "source_sheet": preferred_sheet,
            "process_name": df[activity_col].astype(str).str.strip(),
            "location": df[geography_col] if geography_col else pd.NA,
            "unit": df[unit_col] if unit_col else pd.NA,
            "reference_product": df[product_col] if product_col else pd.NA,
            "category": df.get("Sector", pd.Series([pd.NA] * len(df))),
            "extra_type": df.get("Special Activity Type", pd.Series([pd.NA] * len(df))),
        }
    )
    out["reference_product"] = out["reference_product"].astype(str).replace({"nan": ""}).str.strip()
    out["location"] = out["location"].astype(str).replace({"nan": ""}).str.strip()
    out["unit"] = out["unit"].astype(str).replace({"nan": ""}).str.strip()
    out["category"] = out["category"].astype(str).replace({"nan": ""}).str.strip()
    out["extra_type"] = out["extra_type"].astype(str).replace({"nan": ""}).str.strip()
    out = out[out["process_name"].notna() & (out["process_name"].str.lower() != "nan")].copy()
    out["catalog_source_file"] = path.name
    return out.reset_index(drop=True)


def build_process_catalog(
    ecoinvent_path: Path = DEFAULT_ECOINVENT,
    agribalyse_conv_path: Path = DEFAULT_AGRIBALYSE_CONV,
    agribalyse_bio_path: Path = DEFAULT_AGRIBALYSE_BIO,
    agribalyse_organic_fert_path: Path = DEFAULT_AGRIBALYSE_ORGANIC_FERT,
) -> pd.DataFrame:
    eco = build_ecoinvent_catalog(ecoinvent_path)
    agb = build_agribalyse_catalog(agribalyse_conv_path, agribalyse_bio_path)
    agb_org = build_agribalyse_organic_fertilizer_catalog(agribalyse_organic_fert_path)
    cat = pd.concat([eco, agb, agb_org], ignore_index=True)

    cat["process_name_norm"] = cat["process_name"].map(norm_name)
    cat["reference_product_norm"] = cat["reference_product"].map(norm_name)
    cat["tokens"] = cat["process_name"].map(tokenize_name)
    cat["unit_norm"] = cat["unit"].map(norm_text)
    cat["location_norm"] = cat["location"].map(norm_text)
    if "placeholder_comment" not in cat.columns:
        cat["placeholder_comment"] = ""
    cat["placeholder_comment_norm"] = cat["placeholder_comment"].map(norm_text)

    # Deduplicate exact rows after normalization
    cat = cat.drop_duplicates(
        subset=["database", "database_variant", "process_name_norm", "reference_product_norm", "unit_norm", "location_norm"]
    ).reset_index(drop=True)
    cat["catalog_id"] = [f"cat_{i+1:06d}" for i in range(len(cat))]
    return cat


def _default_agribalyse_organic_fertilizers() -> pd.DataFrame:
    rows = [
        {
            "database": "Agribalyse",
            "database_variant": "organic_curated",
            "source_sheet": "manual_organic_fertilizers",
            "process_name": "a. Manure, from cattle, stocked in concrete surface or pit",
            "location": "GLO",
            "unit": "kg",
            "reference_product": "Cattle manure, solid",
            "category": "organic fertiliser",
            "extra_type": "",
            "catalog_source_file": DEFAULT_AGRIBALYSE_ORGANIC_FERT.name,
            "placeholder_comment": "Cattle, solid",
        },
        {
            "database": "Agribalyse",
            "database_variant": "organic_curated",
            "source_sheet": "manual_organic_fertilizers",
            "process_name": "f. Slurry, from cattle, stocked in silo",
            "location": "GLO",
            "unit": "kg",
            "reference_product": "Cattle slurry, liquid",
            "category": "organic fertiliser",
            "extra_type": "",
            "catalog_source_file": DEFAULT_AGRIBALYSE_ORGANIC_FERT.name,
            "placeholder_comment": "Cattle, liquid",
        },
        {
            "database": "Agribalyse",
            "database_variant": "organic_curated",
            "source_sheet": "manual_organic_fertilizers",
            "process_name": "f. Slurry, from swine, stocked in silo",
            "location": "GLO",
            "unit": "kg",
            "reference_product": "Swine slurry, liquid",
            "category": "organic fertiliser",
            "extra_type": "",
            "catalog_source_file": DEFAULT_AGRIBALYSE_ORGANIC_FERT.name,
            "placeholder_comment": "Swine, liquid",
        },
        {
            "database": "Agribalyse",
            "database_variant": "organic_curated",
            "source_sheet": "manual_organic_fertilizers",
            "process_name": "f. Manure, from poultry, stocked in concrete surface or pit",
            "location": "GLO",
            "unit": "kg",
            "reference_product": "Poultry manure",
            "category": "organic fertiliser",
            "extra_type": "",
            "catalog_source_file": DEFAULT_AGRIBALYSE_ORGANIC_FERT.name,
            "placeholder_comment": "Poultry, droppings",
        },
        {
            "database": "Agribalyse",
            "database_variant": "organic_curated",
            "source_sheet": "manual_organic_fertilizers",
            "process_name": "a. Average compost, from green waste, biowaste, sludge, manure, slurry",
            "location": "GLO",
            "unit": "kg",
            "reference_product": "Compost",
            "category": "organic fertiliser",
            "extra_type": "",
            "catalog_source_file": DEFAULT_AGRIBALYSE_ORGANIC_FERT.name,
            "placeholder_comment": "Compost",
        },
        {
            "database": "Agribalyse",
            "database_variant": "organic_curated",
            "source_sheet": "manual_organic_fertilizers",
            "process_name": "a. Compost, of solid fraction of digestate from manure and green waste",
            "location": "GLO",
            "unit": "kg",
            "reference_product": "Compost from digestate",
            "category": "organic fertiliser",
            "extra_type": "",
            "catalog_source_file": DEFAULT_AGRIBALYSE_ORGANIC_FERT.name,
            "placeholder_comment": "Compost_digestate",
        },
        {
            "database": "Agribalyse",
            "database_variant": "organic_curated",
            "source_sheet": "manual_organic_fertilizers",
            "process_name": "f. Average agricultural digestate",
            "location": "GLO",
            "unit": "kg",
            "reference_product": "Digestate",
            "category": "organic fertiliser",
            "extra_type": "",
            "catalog_source_file": DEFAULT_AGRIBALYSE_ORGANIC_FERT.name,
            "placeholder_comment": "Digestate",
        },
    ]
    return pd.DataFrame(rows)


def build_agribalyse_organic_fertilizer_catalog(path: Path) -> pd.DataFrame:
    if path.exists():
        df = pd.read_csv(path)
    else:
        df = _default_agribalyse_organic_fertilizers()
    required = {
        "database",
        "database_variant",
        "source_sheet",
        "process_name",
        "location",
        "unit",
        "reference_product",
        "category",
        "extra_type",
        "catalog_source_file",
        "placeholder_comment",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Organic fertilizer catalog is missing columns: {sorted(missing)}")
    out = df.copy()
    for col in required:
        out[col] = out[col].astype(str).replace({"nan": ""}).str.strip()
    out = out[out["process_name"].ne("")].copy()
    return out.reset_index(drop=True)


@dataclass
class MatchCandidate:
    catalog_id: str
    database: str
    variant: str
    process_name: str
    reference_product: str
    location: str
    unit: str
    score: float
    reasons: str


def _name_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _token_jaccard(a_tokens: list[str], b_tokens: list[str]) -> float:
    a = set(a_tokens)
    b = set(b_tokens)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _compat_unit(exchange_unit: str, candidate_unit: str) -> float:
    u1 = norm_text(exchange_unit)
    u2 = norm_text(candidate_unit)
    if not u1 or not u2:
        return 0.0
    convertible = {
        ("kg", "ton"),
        ("kg", "t"),
        ("ton", "kg"),
        ("t", "kg"),
        ("g", "kg"),
        ("kg", "g"),
    }
    if u1 == u2:
        return 1.0
    if (u1, u2) in convertible:
        return 0.35
    return -0.25


def _compat_location(exchange_loc: str, candidate_loc: str) -> float:
    e = norm_text(exchange_loc)
    c = norm_text(candidate_loc)
    if not e or not c:
        return 0.0
    if e == c:
        return 1.0
    if e == "glo" and c in {"glo", "row", "rer"}:
        return 0.25
    if c == "glo":
        return 0.1
    return 0.0


def _exchange_domain_hint(row: pd.Series) -> str:
    gc = norm_text(row.get("attr__generalComment", ""))
    nm = norm_text(row.get("attr__name", ""))
    txt = f"{gc} {nm}"
    if any(t in txt for t in ["insecticide", "herbicide", "fungicide", "pesticide"]):
        return "pesticide"
    if any(
        t in txt
        for t in [
            "urea",
            "ammonium",
            "fertilis",
            "fertiliz",
            "map",
            "can",
            "npk",
            "manure",
            "slurry",
            "compost",
            "digestate",
            "organo-mineral",
            "amendment",
            "sludge",
        ]
    ):
        return "fertiliser"
    if "seed" in txt:
        return "seed"
    if "diesel" in txt or "fuel" in txt:
        return "fuel"
    if "water" in txt:
        return "water"
    if "transport" in txt or "truck" in txt or "tractor" in txt:
        return "transport"
    if any(t in txt for t in ["nh3", "n2o", "nox", "co2", "no3", "cadmium", "zinc", "copper", "lead", "nickel", "chrom", "mercury"]):
        return "elementary"
    return ""


ORGANIC_FERTILIZER_PLACEHOLDER_COMMENTS = {
    "Cattle, solid",
    "Cattle, liquid",
    "Swine, liquid",
    "Poultry, droppings",
    "Compost",
    "Compost_digestate",
    "Digestate",
}
ORGANIC_FERT_KEYWORDS = {"manure", "slurry", "compost", "digestate", "effluent", "droppings"}
ORGANIC_FERT_EXCHANGE_KEYWORDS = {
    "manure",
    "slurry",
    "compost",
    "digestate",
    "effluent",
    "droppings",
    "organic fertiliser",
    "organic fertilizer",
    "organo-mineral",
    "amendment",
    "sludge",
}


def _is_organic_fertilizer_exchange(row: pd.Series) -> bool:
    gc = str(row.get("attr__generalComment", "") or "").strip()
    if gc in ORGANIC_FERTILIZER_PLACEHOLDER_COMMENTS:
        return True
    nm = norm_text(row.get("attr__name", ""))
    gc_norm = norm_text(gc)
    txt = f"{nm} {gc_norm}"
    return any(t in txt for t in ORGANIC_FERT_EXCHANGE_KEYWORDS)


def _organic_fertilizer_db_bonus(row: pd.Series, cat_row: pd.Series) -> float:
    if not _is_organic_fertilizer_exchange(row):
        return 0.0
    db = norm_text(cat_row.get("database", ""))
    variant = norm_text(cat_row.get("database_variant", ""))
    if db == "agribalyse":
        if variant in {"unit", "organic", "organic_curated"}:
            return 0.08
        return 0.05
    if db == "ecoinvent":
        return -0.03
    return 0.0


def _organic_relevant_catalog_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    def has_placeholder_tag(row) -> bool:
        return bool(norm_text(row.get("placeholder_comment", "")))

    def has_kw(row) -> bool:
        txt = norm_text(f"{row.get('process_name','')} {row.get('reference_product','')}")
        return any(k in txt for k in ORGANIC_FERT_KEYWORDS)

    mask = df.apply(lambda r: has_placeholder_tag(r) or has_kw(r), axis=1)
    return df[mask].copy()


def _organic_placeholder_bonus(row: pd.Series, cat_row: pd.Series) -> float:
    if not _is_organic_fertilizer_exchange(row):
        return 0.0
    exchange_comment = norm_text(row.get("attr__generalComment", ""))
    candidate_comment = norm_text(cat_row.get("placeholder_comment", ""))
    if not exchange_comment or not candidate_comment:
        return 0.0
    return 0.4 if exchange_comment == candidate_comment else 0.0


def _catalog_domain_hint(cat_row: pd.Series) -> str:
    txt = norm_text(f"{cat_row.get('process_name','')} {cat_row.get('reference_product','')} {cat_row.get('category','')}")
    if any(t in txt for t in ["herbicide", "pesticide", "fungicide", "insecticide"]):
        return "pesticide"
    if any(t in txt for t in ["fertilis", "fertiliz", "urea", "ammonium nitrate", "phosphate", "potash", "npk"]):
        return "fertiliser"
    if "seed" in txt:
        return "seed"
    if "diesel" in txt or "gasoline" in txt:
        return "fuel"
    if "water" in txt:
        return "water"
    if "transport" in txt or "truck" in txt or "tractor" in txt:
        return "transport"
    return ""


def _exchange_match_text(row: pd.Series) -> str:
    name = str(row.get("attr__name", "") or "").strip()
    comment = str(row.get("attr__generalComment", "") or "").strip()
    if comment and comment.lower() != "nan":
        return f"{name} {comment}".strip()
    return name


def _keyword_alignment_bonus(exchange_text_norm: str, candidate_text_norm: str) -> float:
    keys = [
        "manure",
        "slurry",
        "compost",
        "digestate",
        "cattle",
        "swine",
        "poultry",
        "solid",
        "liquid",
    ]
    bonus = 0.0
    for k in keys:
        ex_has = k in exchange_text_norm
        if not ex_has:
            continue
        cand_has = k in candidate_text_norm
        bonus += 0.04 if cand_has else -0.02
    return max(min(bonus, 0.24), -0.16)


def suggest_matches_for_exchange(row: pd.Series, catalog: pd.DataFrame, top_n: int = 5) -> list[MatchCandidate]:
    exchange_name = str(row.get("attr__name", "") or "")
    exchange_match_text = _exchange_match_text(row)
    exchange_match_text_norm = norm_text(exchange_match_text)
    ex_name_norm = norm_name(exchange_match_text)
    ex_tokens = tokenize_name(exchange_match_text)
    ex_unit = str(row.get("attr__unit", "") or "")
    ex_location = str(row.get("attr__location", "") or "")
    domain = _exchange_domain_hint(row)

    if not exchange_name.strip():
        return []
    if domain == "elementary":
        return []

    # Candidate prefilter by unit and token overlap to keep runtime low.
    # For organic/fertiliser-like rows, keep wider unit space (kg/ton mismatches are common).
    unit_norm = norm_text(ex_unit)
    if unit_norm and not _is_organic_fertilizer_exchange(row):
        pre = catalog[(catalog["unit_norm"] == unit_norm) | (catalog["unit_norm"] == "") | (catalog["unit_norm"].isna())].copy()
    else:
        pre = catalog.copy()

    # For organic fertiliser placeholder exchanges, prefer Agribalyse suggestions first.
    # The attached Agribalyse files are product-LCI tables, so fallback to ecoinvent if no viable Agribalyse rows exist.
    if _is_organic_fertilizer_exchange(row):
        pre_agb = pre[pre["database"].astype(str).str.lower() == "agribalyse"].copy()
        pre_agb_rel = _organic_relevant_catalog_rows(pre_agb)
        if len(pre_agb_rel):
            pre = pre_agb_rel
        else:
            pre_eco = pre[pre["database"].astype(str).str.lower() == "ecoinvent"].copy()
            pre_eco_rel = _organic_relevant_catalog_rows(pre_eco)
            pre = pre_eco_rel if len(pre_eco_rel) else pre_eco

    if ex_tokens:
        tokset = set(ex_tokens)

        def overlap_score(toks):
            s = set(toks or [])
            return len(s & tokset)

        pre["_tok_overlap"] = pre["tokens"].map(overlap_score)
        # keep rows with some overlap, but if none exist keep the whole (small-ish) prefiltered set
        if (pre["_tok_overlap"] > 0).any():
            pre = pre[pre["_tok_overlap"] > 0].copy()
        # cap by best overlap
        pre = pre.sort_values("_tok_overlap", ascending=False).head(3000).copy()
    else:
        pre = pre.head(3000).copy()

    cands: list[MatchCandidate] = []
    for _, c in pre.iterrows():
        n_sim = _name_similarity(ex_name_norm, c["process_name_norm"])
        t_j = _token_jaccard(ex_tokens, c["tokens"])
        unit_bonus = _compat_unit(ex_unit, c["unit"])
        loc_bonus = _compat_location(ex_location, c["location"])

        domain_bonus = 0.0
        cat_domain = _catalog_domain_hint(c)
        if domain and cat_domain:
            domain_bonus = 0.5 if domain == cat_domain else -0.2
        organic_db_bonus = _organic_fertilizer_db_bonus(row, c)
        organic_placeholder_bonus = _organic_placeholder_bonus(row, c)
        keyword_bonus = _keyword_alignment_bonus(
            exchange_match_text_norm,
            norm_text(f"{c.get('process_name', '')} {c.get('reference_product', '')}"),
        )

        # reward reference product mention if any exchange tokens appear there
        ref_tokens = set(tokenize_name(c.get("reference_product", "")))
        ref_overlap = len(ref_tokens & set(ex_tokens)) / max(1, len(set(ex_tokens))) if ex_tokens else 0.0

        score = (
            0.55 * n_sim
            + 0.25 * t_j
            + 0.10 * ref_overlap
            + 0.05 * max(unit_bonus, 0)
            + 0.03 * max(loc_bonus, 0)
            + 0.02 * max(domain_bonus, 0)
            + organic_db_bonus
            + organic_placeholder_bonus
            + keyword_bonus
            + min(0.0, unit_bonus) * 0.10
            + min(0.0, domain_bonus) * 0.10
        )

        reasons = []
        if t_j > 0:
            reasons.append(f"token_j={t_j:.2f}")
        reasons.append(f"name={n_sim:.2f}")
        if unit_bonus:
            reasons.append(f"unit={'+' if unit_bonus>0 else ''}{unit_bonus:.2f}")
        if loc_bonus:
            reasons.append(f"loc=+{loc_bonus:.2f}")
        if domain_bonus:
            reasons.append(f"domain={'+' if domain_bonus>0 else ''}{domain_bonus:.2f}")
        if organic_db_bonus:
            reasons.append(f"orgdb={'+' if organic_db_bonus>0 else ''}{organic_db_bonus:.2f}")
        if organic_placeholder_bonus:
            reasons.append(f"orgmap=+{organic_placeholder_bonus:.2f}")
        if keyword_bonus:
            reasons.append(f"kw={'+' if keyword_bonus>0 else ''}{keyword_bonus:.2f}")

        cands.append(
            MatchCandidate(
                catalog_id=str(c["catalog_id"]),
                database=str(c["database"]),
                variant=str(c["database_variant"]),
                process_name=str(c["process_name"]),
                reference_product="" if pd.isna(c.get("reference_product", "")) else str(c.get("reference_product", "")),
                location="" if pd.isna(c.get("location", "")) else str(c.get("location", "")),
                unit="" if pd.isna(c.get("unit", "")) else str(c.get("unit", "")),
                score=float(score),
                reasons="; ".join(reasons),
            )
        )

    cands.sort(key=lambda x: x.score, reverse=True)
    # Fallback for organic fertiliser rows if Agribalyse-first branch produced no suggestions.
    if not cands and _is_organic_fertilizer_exchange(row):
        eco_subset = catalog[catalog["database"].astype(str).str.lower() == "ecoinvent"].copy()
        eco_subset = _organic_relevant_catalog_rows(eco_subset)
        if eco_subset.empty:
            return []
        return suggest_matches_for_exchange_with_catalog_subset(row, eco_subset, top_n=top_n)
    # de-duplicate identical suggestions
    out = []
    seen = set()
    for c in cands:
        key = (c.database, c.process_name, c.location, c.unit)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= top_n:
            break
    return out


def suggest_matches_for_exchange_with_catalog_subset(row: pd.Series, catalog_subset: pd.DataFrame, top_n: int = 5) -> list[MatchCandidate]:
    # Wrapper to reuse the same scorer without Agribalyse-first logic recursion.
    # Temporarily bypass by copying row and removing organic placeholder signal? simpler: inline reduced logic via local call on subset after monkey patch impossible.
    exchange_name = str(row.get("attr__name", "") or "")
    exchange_match_text = _exchange_match_text(row)
    exchange_match_text_norm = norm_text(exchange_match_text)
    ex_name_norm = norm_name(exchange_match_text)
    ex_tokens = tokenize_name(exchange_match_text)
    ex_unit = str(row.get("attr__unit", "") or "")
    ex_location = str(row.get("attr__location", "") or "")
    domain = _exchange_domain_hint(row)
    if not exchange_name.strip() or domain == "elementary":
        return []
    pre = catalog_subset.copy()
    unit_norm = norm_text(ex_unit)
    if unit_norm and "unit_norm" in pre.columns and not _is_organic_fertilizer_exchange(row):
        pre = pre[(pre["unit_norm"] == unit_norm) | (pre["unit_norm"] == "") | (pre["unit_norm"].isna())].copy()
    if ex_tokens:
        tokset = set(ex_tokens)
        pre["_tok_overlap"] = pre["tokens"].map(lambda toks: len(set(toks or []) & tokset))
        if (pre["_tok_overlap"] > 0).any():
            pre = pre[pre["_tok_overlap"] > 0].copy()
        pre = pre.sort_values("_tok_overlap", ascending=False).head(3000).copy()
    else:
        pre = pre.head(3000).copy()
    cands: list[MatchCandidate] = []
    for _, c in pre.iterrows():
        n_sim = _name_similarity(ex_name_norm, c["process_name_norm"])
        t_j = _token_jaccard(ex_tokens, c["tokens"])
        unit_bonus = _compat_unit(ex_unit, c["unit"])
        loc_bonus = _compat_location(ex_location, c["location"])
        domain_bonus = 0.0
        cat_domain = _catalog_domain_hint(c)
        if domain and cat_domain:
            domain_bonus = 0.5 if domain == cat_domain else -0.2
        organic_db_bonus = _organic_fertilizer_db_bonus(row, c)
        keyword_bonus = _keyword_alignment_bonus(
            exchange_match_text_norm,
            norm_text(f"{c.get('process_name', '')} {c.get('reference_product', '')}"),
        )
        ref_tokens = set(tokenize_name(c.get("reference_product", "")))
        ref_overlap = len(ref_tokens & set(ex_tokens)) / max(1, len(set(ex_tokens))) if ex_tokens else 0.0
        score = (
            0.55 * n_sim + 0.25 * t_j + 0.10 * ref_overlap
            + 0.05 * max(unit_bonus, 0) + 0.03 * max(loc_bonus, 0) + 0.02 * max(domain_bonus, 0)
            + organic_db_bonus
            + keyword_bonus
            + min(0.0, unit_bonus) * 0.10 + min(0.0, domain_bonus) * 0.10
        )
        reasons = [f"name={n_sim:.2f}"]
        if t_j > 0:
            reasons.insert(0, f"token_j={t_j:.2f}")
        cands.append(
            MatchCandidate(
                catalog_id=str(c["catalog_id"]),
                database=str(c["database"]),
                variant=str(c["database_variant"]),
                process_name=str(c["process_name"]),
                reference_product="" if pd.isna(c.get("reference_product", "")) else str(c.get("reference_product", "")),
                location="" if pd.isna(c.get("location", "")) else str(c.get("location", "")),
                unit="" if pd.isna(c.get("unit", "")) else str(c.get("unit", "")),
                score=float(score),
                reasons="; ".join(reasons),
            )
        )
    cands.sort(key=lambda x: x.score, reverse=True)
    out, seen = [], set()
    for c in cands:
        key = (c.database, c.process_name, c.location, c.unit)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= top_n:
            break
    return out


def build_match_workbook(
    exchanges_path: Path = DEFAULT_EXCHANGES,
    catalog_csv_out: Path = DEFAULT_CATALOG_CSV,
    matches_xlsx_out: Path = DEFAULT_MATCH_XLSX,
    top_n: int = DEFAULT_TOP_N,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    def _emit(stage: str, current: int, total: int) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(stage, int(current), int(total))
        except Exception:
            # Progress updates are best-effort and must not break matching.
            pass

    _emit("prepare_catalog", 0, 1)
    catalog = build_process_catalog()
    catalog.to_csv(catalog_csv_out, index=False, encoding="utf-8-sig")
    _emit("prepare_catalog", 1, 1)

    _emit("load_exchanges", 0, 1)
    ex = pd.read_excel(exchanges_path)
    ex = ex.rename(columns={c: str(c).strip() for c in ex.columns})
    # Only consider rows with a non-empty XML location for process-name matching.
    if "attr__location" in ex.columns:
        loc = ex["attr__location"].astype(str).replace({"nan": ""}).str.strip()
        ex = ex[loc.ne("")].copy()
    # Keep technosphere rows only: ignore elementary-emission exchanges categorized as air/water/soil.
    if "attr__category" in ex.columns:
        cat = ex["attr__category"].astype(str).replace({"nan": ""}).str.strip().str.lower()
        ex = ex[~cat.isin({"air", "water", "soil"})].copy()
    _emit("load_exchanges", 1, 1)

    review_rows = []
    total_rows = max(int(len(ex)), 1)
    _emit("matching", 0, total_rows)
    for idx, (_, row) in enumerate(ex.iterrows(), start=1):
        name = str(row.get("attr__name", "") or "").strip()
        candidates = suggest_matches_for_exchange(row, catalog, top_n=top_n)
        base = row.to_dict()
        base["match_status"] = ""
        base["approved_database"] = ""
        base["approved_process_name"] = ""
        base["approved_location"] = ""
        base["approved_unit"] = ""
        base["match_notes"] = ""
        base["exchange_domain_hint"] = _exchange_domain_hint(row)
        base["match_candidate_count"] = len(candidates)
        for i in range(top_n):
            n = i + 1
            if i < len(candidates):
                c = candidates[i]
                base[f"suggest_{n}_score"] = round(c.score, 4)
                base[f"suggest_{n}_database"] = c.database
                base[f"suggest_{n}_variant"] = c.variant
                base[f"suggest_{n}_process_name"] = c.process_name
                base[f"suggest_{n}_reference_product"] = c.reference_product
                base[f"suggest_{n}_location"] = c.location
                base[f"suggest_{n}_unit"] = c.unit
                base[f"suggest_{n}_reasons"] = c.reasons
            else:
                for suffix in [
                    "score",
                    "database",
                    "variant",
                    "process_name",
                    "reference_product",
                    "location",
                    "unit",
                    "reasons",
                ]:
                    base[f"suggest_{n}_{suffix}"] = ""

        # simple auto-flag for very strong exact-ish match
        if candidates and candidates[0].score >= 0.92:
            base["match_status"] = "auto_high_conf"
            base["approved_database"] = candidates[0].database
            base["approved_process_name"] = candidates[0].process_name
            base["approved_location"] = candidates[0].location
            base["approved_unit"] = candidates[0].unit
        elif not name:
            base["match_status"] = "no_name"
        elif _exchange_domain_hint(row) == "elementary":
            base["match_status"] = "skip_elementary_flow"
        else:
            base["match_status"] = "review"

        review_rows.append(base)
        _emit("matching", idx, total_rows)

    review_df = pd.DataFrame(review_rows)

    catalog_preview = catalog[
        [
            "catalog_id",
            "database",
            "database_variant",
            "process_name",
            "reference_product",
            "location",
            "unit",
            "category",
            "extra_type",
        ]
    ].copy()

    _emit("write_workbook", 0, 1)
    with pd.ExcelWriter(matches_xlsx_out, engine="openpyxl") as writer:
        review_df.to_excel(writer, index=False, sheet_name="exchange_matches")
        # summary
        summary = (
            review_df.groupby(["match_status", "exchange_domain_hint"], dropna=False)
            .size()
            .reset_index(name="rows")
            .sort_values(["match_status", "rows"], ascending=[True, False])
        )
        summary.to_excel(writer, index=False, sheet_name="summary")
        catalog_preview.head(5000).to_excel(writer, index=False, sheet_name="catalog_preview")
    _emit("write_workbook", 1, 1)
    _emit("done", 1, 1)

    return catalog, review_df


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build process catalog and suggest LCI database process names for exchanges_table.xlsx")
    p.add_argument("--exchanges", type=Path, default=DEFAULT_EXCHANGES)
    p.add_argument("--catalog-csv", type=Path, default=DEFAULT_CATALOG_CSV)
    p.add_argument("--matches-xlsx", type=Path, default=DEFAULT_MATCH_XLSX)
    p.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    return p


def main() -> int:
    args = build_parser().parse_args()
    catalog, review_df = build_match_workbook(
        exchanges_path=args.exchanges,
        catalog_csv_out=args.catalog_csv,
        matches_xlsx_out=args.matches_xlsx,
        top_n=args.top_n,
    )
    print(f"Catalog rows: {len(catalog):,} -> {args.catalog_csv}")
    print(f"Match rows: {len(review_df):,} -> {args.matches_xlsx}")
    print("Match status counts:")
    print(review_df["match_status"].value_counts(dropna=False).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
