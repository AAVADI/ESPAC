from __future__ import annotations

import argparse
import copy
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import yaml

ECO_NS = "http://www.EcoInvent.org/EcoSpold01"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
ET.register_namespace("", ECO_NS)
ET.register_namespace("xsi", XSI_NS)
NS = {"eco": ECO_NS}


def weighted_quantile(values: pd.Series, weights: pd.Series, q: float) -> float:
    v = pd.to_numeric(values, errors="coerce")
    w = pd.to_numeric(weights, errors="coerce")
    m = v.notna() & w.notna() & (w > 0)
    if not m.any():
        return float("nan")
    df = pd.DataFrame({"v": v[m].astype(float), "w": w[m].astype(float)}).sort_values("v")
    cdf = df["w"].cumsum() / df["w"].sum()
    return float(df.loc[cdf.ge(q), "v"].iloc[0]) if (cdf >= q).any() else float(df["v"].iloc[-1])


def safe_slug(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "item"


def parse_comment_tokens(expr: str) -> list[str]:
    if not expr:
        return []
    return [t.strip() for t in expr.split("+") if t.strip()]


ALIAS_MAP: Dict[str, str] = {
    "kgCH4_livestock_total_per_1kg_product": "ch4_enteric_kg_per_kg_product",
    "kgN2O_manure_mgmt_total_per_1kg_product": "n2o_direct_kg_per_kg_product",
    "Water_l_per_1kg_product": "water_l_per_kg_product",
    "Electricity_kWh_per_1kg_product": "electricity_kwh_per_kg_product",
    "Area_ha_per_1kg_product": "area_ha_per_kg_product",
    "Total_feed_kg_per_1kg_product": "total_feed_kg_per_kg_product",
    "Supplement_feed_kg_per_1kg_product": "supplement_feed_kg_per_kg_product",
    "Pasture_feed_kg_per_1kg_product": "pasture_feed_kg_per_kg_product",
    "Unmatched_pasture_feed_kg_per_1kg_product": "unmatched_pasture_feed_kg_per_kg_product",
    "Animals_total_live_weight_kg_per_1kg_product": "animals_total_live_weight_kg_per_kg_product",
    "kgNH3_manure_mgmt_total_per_1kg_product": "nh3_total_kg_per_kg_product",
    "kgNH3_manure_housing_storage_yard_per_1kg_product": "nh3_housing_kg_per_kg_product",
    "kgNH3_grazing_per_1kg_product": "nh3_grazing_kg_per_kg_product",
    "kgNOx_manure_mgmt_as_NO2_per_1kg_product": "nox_as_no2_kg_per_kg_product",
    "kgCH4_manure_mgmt_total_per_1kg_product": "ch4_manure_kg_per_kg_product",
}
REVERSE_ALIAS_MAP: Dict[str, str] = {v: k for k, v in ALIAS_MAP.items()}

LEGACY_STRATEGY_PRODUCTS = {
    "cattle_live",
    "donkey_live",
    "eggs",
    "goat_live",
    "horse_live",
    "meat_poultry",
    "milk",
    "mule_live",
    "ovine_live",
    "swine_live",
}


def classify_product(product: str) -> str:
    p = (product or "").lower()
    if p in {"milk"}:
        return "milk"
    if p in {"eggs"}:
        return "eggs"
    if p in {"meat_poultry"}:
        return "poultry"
    if p in {"swine_live"}:
        return "swine"
    if p in {"ovine_live", "goat_live"}:
        return "small_ruminant"
    if p in {"cattle_live", "cattle_meat"}:
        return "cattle"
    if p in {"other_livestock_live"}:
        return "small_ruminant"
    return "other_meat"


def choose_template(product: str, template_dir: Path) -> Path:
    product = (product or "").lower()
    if product == "eggs":
        return template_dir / "livestock00001.XML"
    if product == "milk":
        return template_dir / "livestock00003.XML"
    return template_dir / "livestock00002.XML"


def get_unc_row(unc_df: pd.DataFrame, row: pd.Series, row_idx: Optional[int] = None) -> Optional[pd.Series]:
    if unc_df.empty:
        return None
    # Original pipeline layout: uncertainty rows align by index with main table.
    if row_idx is not None and ("scope" not in unc_df.columns):
        if 0 <= row_idx < len(unc_df):
            return unc_df.iloc[row_idx]
    product = str(row.get("product", ""))
    prov = str(row.get("ual_prov", ""))
    product_col = "product" if "product" in unc_df.columns else ("Product" if "Product" in unc_df.columns else None)
    prov_col = "ual_prov" if "ual_prov" in unc_df.columns else ("Province" if "Province" in unc_df.columns else None)
    scope_col = "scope" if "scope" in unc_df.columns else None
    if scope_col and product_col and prov_col:
        p = unc_df[(unc_df[scope_col] == "province") & (unc_df[product_col].astype(str) == product) & (unc_df[prov_col].astype(str) == prov)]
    else:
        p = pd.DataFrame()
    if not p.empty:
        return p.iloc[0]
    if scope_col and product_col:
        n = unc_df[(unc_df[scope_col] == "national") & (unc_df[product_col].astype(str) == product)]
    elif product_col:
        n = unc_df[unc_df[product_col].astype(str) == product]
    else:
        n = pd.DataFrame()
    if not n.empty:
        return n.iloc[0]
    return None


def resolve_value(token: str, row: pd.Series) -> float:
    if token in row.index:
        return float(pd.to_numeric(pd.Series([row[token]]), errors="coerce").fillna(0).iloc[0])
    col = ALIAS_MAP.get(token, token)
    if col in row.index:
        return float(pd.to_numeric(pd.Series([row[col]]), errors="coerce").fillna(0).iloc[0])
    rev = REVERSE_ALIAS_MAP.get(token, token)
    if rev in row.index:
        return float(pd.to_numeric(pd.Series([row[rev]]), errors="coerce").fillna(0).iloc[0])
    return 0.0


def resolve_unc(token: str, unc_row: Optional[pd.Series]) -> tuple[Optional[float], Optional[float]]:
    if unc_row is None:
        return None, None
    if token in unc_row.index or f"{token}__p05" in unc_row.index or f"{token}__minValue" in unc_row.index:
        col = token
    else:
        col = ALIAS_MAP.get(token, token)
        if col not in unc_row.index and f"{col}__p05" not in unc_row.index and f"{col}__minValue" not in unc_row.index:
            col = REVERSE_ALIAS_MAP.get(token, token)
    candidates: list[tuple[float, float]] = []
    # Prefer aggregate min/max spread when available, then quantiles.
    pairs = [
        (f"{col}__min", f"{col}__max"),
        (f"{col}__minValue", f"{col}__maxValue"),
        (f"{col}__p05", f"{col}__p95"),
    ]
    for lo_key, hi_key in pairs:
        if lo_key in unc_row.index and hi_key in unc_row.index:
            lo_v = pd.to_numeric(pd.Series([unc_row[lo_key]]), errors="coerce").iloc[0]
            hi_v = pd.to_numeric(pd.Series([unc_row[hi_key]]), errors="coerce").iloc[0]
            if pd.notna(lo_v) and pd.notna(hi_v):
                lo_f, hi_f = float(lo_v), float(hi_v)
                if hi_f < lo_f:
                    lo_f, hi_f = hi_f, lo_f
                candidates.append((lo_f, hi_f))
    if candidates:
        # Keep the widest valid range to avoid flat uncertainty from narrow quantiles.
        candidates.sort(key=lambda x: (x[1] - x[0]), reverse=True)
        return candidates[0]
    return None, None


def aggregate_national_product(lci: pd.DataFrame) -> pd.DataFrame:
    out_rows = []
    numeric_cols = [c for c in lci.columns if pd.api.types.is_numeric_dtype(lci[c])]
    intensity_cols = [c for c in numeric_cols if c.endswith("_per_kg_product")]
    for product, part in lci.groupby("product", dropna=False):
        row = {"product": product, "identificador": "national_aggregate", "ual_prov": "all_provinces"}
        output_col = "product_output_kg_year" if "product_output_kg_year" in part.columns else None
        if output_col is None:
            output = pd.Series([1.0] * len(part), index=part.index, dtype=float)
        else:
            output = pd.to_numeric(part[output_col], errors="coerce").fillna(0.0)
        output_sum = float(output.sum())
        row["product_output_kg_year"] = output_sum
        if output_sum > 0:
            for c in intensity_cols:
                vals = pd.to_numeric(part.get(c), errors="coerce").fillna(0.0)
                row[c] = float((vals * output).sum() / output_sum)
        # keep robust median for non-intensity numeric fields
        for c in numeric_cols:
            if c in intensity_cols or c == "product_output_kg_year":
                continue
            row[c] = float(pd.to_numeric(part.get(c), errors="coerce").median())
        out_rows.append(row)
    return pd.DataFrame(out_rows)


def build_stock_overrides_from_v2(v2_lci_path: Path) -> Dict[str, float]:
    """
    Build product-level stock intensity overrides from class-harmonized V2 rows.
    Preference order:
    - attributed_live_weight_kg / product_output_kg_year (if available)
    - animals_total_live_weight_kg_per_kg_product
    Aggregation is production-weighted mean over rows.
    """
    if not v2_lci_path.exists():
        return {}
    df = pd.read_csv(v2_lci_path, low_memory=False)
    if "product" not in df.columns:
        return {}
    out: Dict[str, float] = {}
    for product, part in df.groupby("product", dropna=False):
        p = part.copy()
        output = pd.to_numeric(p.get("product_output_kg_year"), errors="coerce").fillna(0.0)
        if "attributed_live_weight_kg" in p.columns:
            lw = pd.to_numeric(p.get("attributed_live_weight_kg"), errors="coerce").fillna(0.0)
            with pd.option_context("mode.use_inf_as_na", True):
                intensity = (lw / output.replace(0, pd.NA)).astype(float)
        else:
            intensity = pd.to_numeric(p.get("animals_total_live_weight_kg_per_kg_product"), errors="coerce").fillna(0.0)
        valid = intensity.notna() & (output > 0)
        if not valid.any():
            continue
        v = float((intensity[valid] * output[valid]).sum() / output[valid].sum())
        out[str(product)] = v
    return out


def build_residual_animal_overrides_from_v2(v2_lci_path: Path) -> Dict[str, Dict[str, float]]:
    """
    Residual animal-class contribution not already represented by:
    - milk: vacas ordeñadas (attributed_live_weight_kg)
    - eggs: gallinas ponedoras (attributed_live_weight_kg)
    Returned values are per-kg-product intensities (mean/min/max) for exchange #2
    in milk/eggs templates.
    """
    if not v2_lci_path.exists():
        return {}
    df = pd.read_csv(v2_lci_path, low_memory=False)
    if "product" not in df.columns or "identificador" not in df.columns:
        return {}
    out: Dict[str, Dict[str, float]] = {}

    def _weighted_residual(product: str, base_product: str) -> Optional[Dict[str, float]]:
        tgt = df[df["product"].astype(str) == product].copy()
        base = df[df["product"].astype(str) == base_product].copy()
        if tgt.empty or base.empty:
            return None
        tgt["product_output_kg_year"] = pd.to_numeric(tgt.get("product_output_kg_year"), errors="coerce").fillna(0.0)
        tgt["attributed_live_weight_kg"] = pd.to_numeric(tgt.get("attributed_live_weight_kg"), errors="coerce").fillna(0.0)
        base["product_output_kg_year"] = pd.to_numeric(base.get("product_output_kg_year"), errors="coerce").fillna(0.0)
        base["animals_total_live_weight_kg_per_kg_product"] = pd.to_numeric(
            base.get("animals_total_live_weight_kg_per_kg_product"), errors="coerce"
        ).fillna(0.0)
        # Reconstruct species total LW from species product rows.
        base["species_total_lw_kg"] = base["product_output_kg_year"] * base["animals_total_live_weight_kg_per_kg_product"]
        bmap = (
            base.groupby("identificador", as_index=False)["species_total_lw_kg"]
            .sum()
            .set_index("identificador")["species_total_lw_kg"]
            .to_dict()
        )
        tgt["species_total_lw_kg"] = tgt["identificador"].map(bmap).fillna(0.0)
        tgt["residual_lw_kg"] = (tgt["species_total_lw_kg"] - tgt["attributed_live_weight_kg"]).clip(lower=0.0)
        valid = tgt["product_output_kg_year"] > 0
        if not valid.any():
            return None
        residual_int = tgt.loc[valid, "residual_lw_kg"] / tgt.loc[valid, "product_output_kg_year"]
        w = tgt.loc[valid, "product_output_kg_year"]
        if float(w.sum()) <= 0:
            return None
        mean_v = float((residual_int * w).sum() / w.sum())
        # Use weighted p05/p95 as robust uncertainty bounds for aggregated exports.
        min_v = weighted_quantile(residual_int, w, 0.05)
        max_v = weighted_quantile(residual_int, w, 0.95)
        if pd.isna(min_v):
            min_v = float(residual_int.min())
        if pd.isna(max_v):
            max_v = float(residual_int.max())
        if max_v < min_v:
            min_v, max_v = max_v, min_v
        if max_v == min_v:
            eps = max(abs(mean_v) * 1e-3, 1e-9)
            min_v = mean_v - eps
            max_v = mean_v + eps
        return {"mean": mean_v, "min": min_v, "max": max_v}

    milk_res = _weighted_residual("milk", "cattle_meat")
    eggs_res = _weighted_residual("eggs", "meat_poultry")
    if milk_res is not None:
        out["milk"] = milk_res
    if eggs_res is not None:
        out["eggs"] = eggs_res
    return out


def build_replacement_animal_overrides_from_v2(v2_lci_path: Path, stock_path: Path) -> Dict[str, Dict[str, float]]:
    """
    Strategy 10: replacement-animal demand for milk/eggs only.
    Uses V2 farm-level product intensities and class stock composition (no v1 dependency).

    milk replacement basis:
      replacement female young stock (cattle_ternera + cattle_vacona)
      relative to producing cows (cattle_vaca)

    eggs replacement basis:
      reproductive poultry stock (breeder_hen)
      relative to producing layers (layer_hen)
    """
    if (not v2_lci_path.exists()) or (not stock_path.exists()):
        return {}
    v2 = pd.read_csv(v2_lci_path, low_memory=False)
    stock = pd.read_csv(stock_path, low_memory=False)
    if {"product", "identificador", "product_output_kg_year", "attributed_live_weight_kg"} - set(v2.columns):
        return {}
    if {"identificador", "animal_class", "total_live_weight_kg"} - set(stock.columns):
        return {}

    stock = stock.copy()
    stock["identificador"] = stock["identificador"].astype(str)
    stock["total_live_weight_kg"] = pd.to_numeric(stock["total_live_weight_kg"], errors="coerce").fillna(0.0)
    piv = (
        stock.pivot_table(
            index="identificador",
            columns="animal_class",
            values="total_live_weight_kg",
            aggfunc="sum",
            fill_value=0.0,
        )
        .reset_index()
    )

    def _aggregate(product: str, producer_col: str, replacement_cols: list[str]) -> Optional[Dict[str, float]]:
        p = v2[v2["product"].astype(str) == product].copy()
        if p.empty:
            return None
        p["identificador"] = p["identificador"].astype(str)
        p["product_output_kg_year"] = pd.to_numeric(p["product_output_kg_year"], errors="coerce").fillna(0.0)
        p["attributed_live_weight_kg"] = pd.to_numeric(p["attributed_live_weight_kg"], errors="coerce").fillna(0.0)
        p = p.merge(piv, on="identificador", how="left")
        for c in [producer_col] + replacement_cols:
            if c not in p.columns:
                p[c] = 0.0
            p[c] = pd.to_numeric(p[c], errors="coerce").fillna(0.0)

        valid = p["product_output_kg_year"] > 0
        if not valid.any():
            return None
        px = p.loc[valid].copy()
        prod_lw = px[producer_col]
        repl_lw = px[replacement_cols].sum(axis=1)
        attr_int = px["attributed_live_weight_kg"] / px["product_output_kg_year"]
        ratio = repl_lw / prod_lw.replace(0, pd.NA)
        repl_int = (attr_int * ratio).replace([float("inf"), float("-inf")], pd.NA).fillna(0.0)
        w = px["product_output_kg_year"]
        if float(w.sum()) <= 0:
            return None
        mean_v = float((repl_int * w).sum() / w.sum())
        min_v = weighted_quantile(repl_int, w, 0.05)
        max_v = weighted_quantile(repl_int, w, 0.95)
        if pd.isna(min_v):
            min_v = float(repl_int.min())
        if pd.isna(max_v):
            max_v = float(repl_int.max())
        if max_v < min_v:
            min_v, max_v = max_v, min_v
        if max_v == min_v:
            eps = max(abs(mean_v) * 1e-3, 1e-9)
            min_v = mean_v - eps
            max_v = mean_v + eps
        return {"mean": mean_v, "min": min_v, "max": max_v}

    out: Dict[str, Dict[str, float]] = {}
    milk = _aggregate("milk", "cattle_vaca", ["cattle_ternera", "cattle_vacona"])
    eggs = _aggregate("eggs", "layer_hen", ["breeder_hen"])
    if milk is not None:
        out["milk"] = milk
    if eggs is not None:
        out["eggs"] = eggs
    return out


def build_eggs_replacement_override_from_literature(
    v2_lci_path: Path,
    config_path: Path,
    base_overrides: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, Dict[str, float]]:
    """
    Build eggs exchange #2 override from ESPAC egg-producing stock intensity scaled by
    literature replacement rates in the YAML config.
    """
    if (not v2_lci_path.exists()) or (not config_path.exists()):
        return {}
    with config_path.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    rr = ((cfg.get("livestock_replacement_rates") or {}).get("laying_hen") or {})
    mean_rate = float(rr.get("annual_replacement_rate", 0.67))
    min_rate = float(rr.get("min_rate", mean_rate))
    max_rate = float(rr.get("max_rate", mean_rate))
    if max_rate < min_rate:
        min_rate, max_rate = max_rate, min_rate

    # Use the already harmonized/stable eggs base intensity when available.
    if base_overrides and "eggs" in base_overrides:
        b = base_overrides["eggs"]
        return {
            "eggs": {
                "mean": float(b["mean"]) * mean_rate,
                "min": float(b["mean"]) * min_rate,
                "max": float(b["mean"]) * max_rate,
            }
        }

    v2 = pd.read_csv(v2_lci_path, low_memory=False)
    p = v2[v2["product"].astype(str) == "eggs"].copy()
    if p.empty:
        return {}
    p["product_output_kg_year"] = pd.to_numeric(p.get("product_output_kg_year"), errors="coerce").fillna(0.0)
    p["animals_total_live_weight_kg_per_kg_product"] = pd.to_numeric(
        p.get("animals_total_live_weight_kg_per_kg_product"), errors="coerce"
    ).fillna(0.0)
    valid = p["product_output_kg_year"] > 0
    if not valid.any():
        return {}
    px = p.loc[valid].copy()
    base_int = px["animals_total_live_weight_kg_per_kg_product"]
    w = px["product_output_kg_year"]
    mean_base = float((base_int * w).sum() / w.sum())
    return {
        "eggs": {
            "mean": mean_base * mean_rate,
            "min": mean_base * min_rate,
            "max": mean_base * max_rate,
        }
    }


def render_xml(
    template_path: Path,
    row: pd.Series,
    unc_row: Optional[pd.Series],
    residual_animal_overrides: Optional[Dict[str, Dict[str, float]]] = None,
    replacement_animal_overrides: Optional[Dict[str, Dict[str, float]]] = None,
    strategy: int = 9,
) -> ET.ElementTree:
    tree = ET.parse(template_path)
    root = tree.getroot()

    ref = root.find(".//eco:referenceFunction", NS)
    process_name = str(row.get("process_name", "") or "").strip()
    if not process_name:
        process_name = f"product: {str(row.get('product', 'livestock')).strip()} | summary: strategy_9"
    if ref is not None:
        prod = str(row.get("product", "livestock"))
        prov = str(row.get("ual_prov", "EC")) or "EC"
        ref.set("name", process_name)
        ref.set("localName", process_name)
        # Keep SimaPro-compatible category routing aligned with v1 exports.
        ref.set("subCategory", "ECUADOR")
        ref.set("localSubCategory", "ECUADOR")

    geo = root.find(".//eco:geography", NS)
    if geo is not None:
        geo.set("location", "EC")

    exchanges = root.findall(".//eco:exchange", NS)
    by_number = {ex.attrib.get("number"): ex for ex in exchanges}
    pclass = classify_product(str(row.get("product", "")))

    # Keep reference product exactly at 1 kg FU.
    for ex in exchanges:
        og = ex.find("eco:outputGroup", NS)
        if og is not None and (og.text or "").strip() == "0":
            ex.set("name", process_name)
            # SimaPro expects reference product exchange location to match geography.
            ex.set("location", "EC")
            ex.set("meanValue", "1")
            ex.attrib.pop("minimum", None)
            ex.attrib.pop("maximum", None)
            ex.attrib.pop("minValue", None)
            ex.attrib.pop("maxValue", None)
            ex.attrib.pop("uncertaintyType", None)

    # Also keep activityName aligned with original naming pattern.
    for aname in root.findall(".//eco:activityName", NS):
        aname.text = process_name

    def set_exchange(num: str, tokens: list[str]) -> None:
        ex = by_number.get(num)
        if ex is None:
            return
        total = 0.0
        los = []
        his = []
        for t in tokens:
            total += resolve_value(t, row)
            lo, hi = resolve_unc(t, unc_row)
            if lo is not None:
                los.append(lo)
            if hi is not None:
                his.append(hi)
        ex.set("meanValue", f"{total:.12g}")
        if los and his:
            lo_sum = float(sum(los))
            hi_sum = float(sum(his))
            if hi_sum < lo_sum:
                lo_sum, hi_sum = hi_sum, lo_sum
            # Never export flat uncertainty for aggregated values.
            if hi_sum == lo_sum:
                eps = max(abs(total) * 1e-3, 1e-9)
                lo_sum = total - eps
                hi_sum = total + eps
            # Guard against formatting collapse (different floats serialized as equal text).
            lo_txt = f"{lo_sum:.12g}"
            hi_txt = f"{hi_sum:.12g}"
            if lo_txt == hi_txt:
                eps = max(abs(total) * 1e-3, 1e-9)
                lo_sum = total - eps
                hi_sum = total + eps
                lo_txt = f"{lo_sum:.12g}"
                hi_txt = f"{hi_sum:.12g}"
            ex.set("uncertaintyType", "3")
            ex.set("minValue", lo_txt)
            ex.set("maxValue", hi_txt)
        else:
            ex.set("uncertaintyType", "0")
            ex.attrib.pop("minValue", None)
            ex.attrib.pop("maxValue", None)

    def zero_exchange(num: str) -> None:
        ex = by_number.get(num)
        if ex is None:
            return
        ex.set("meanValue", "0")
        ex.set("uncertaintyType", "0")
        ex.attrib.pop("minValue", None)
        ex.attrib.pop("maxValue", None)

    # Explicit, meaningful exchange population by template.
    tname = template_path.name.lower()
    if tname == "livestock00001.xml":  # eggs
        # Keep animal exchange only for residual non-layer classes to avoid double counting.
        ex2_stats = None
        if strategy == 9 and replacement_animal_overrides and "eggs" in replacement_animal_overrides:
            ex2_stats = replacement_animal_overrides["eggs"]
        elif residual_animal_overrides and "eggs" in residual_animal_overrides:
            ex2_stats = residual_animal_overrides["eggs"]
        if ex2_stats is not None:
            ex2 = by_number.get("2")
            if ex2 is not None:
                eggs_stats = ex2_stats
                ex2.set("meanValue", f"{float(eggs_stats['mean']):.12g}")
                ex2.set("name", f"product: meat_poultry | summary: strategy_{strategy}")
                ex2.set("uncertaintyType", "3")
                ex2.set("minValue", f"{float(eggs_stats['min']):.12g}")
                ex2.set("maxValue", f"{float(eggs_stats['max']):.12g}")
        else:
            zero_exchange("2")
        set_exchange("3", ["water_l_per_kg_product"])
        set_exchange("4", ["electricity_kwh_per_kg_product"])
        set_exchange("5", ["total_feed_kg_per_kg_product"])
        set_exchange("6", ["area_ha_per_kg_product"])
        set_exchange("7", ["area_ha_per_kg_product"])
        set_exchange("8", ["area_ha_per_kg_product"])
        set_exchange("9", ["ch4_enteric_kg_per_kg_product"])
        set_exchange("10", ["nh3_total_kg_per_kg_product", "nh3_housing_kg_per_kg_product", "nh3_grazing_kg_per_kg_product"])
        set_exchange("11", ["nox_as_no2_kg_per_kg_product"])
        set_exchange("12", ["n2o_direct_kg_per_kg_product"])

    elif tname == "livestock00003.xml":  # milk
        # Keep animal exchange only for residual non-milking classes to avoid double counting.
        ex2_stats = None
        if residual_animal_overrides and "milk" in residual_animal_overrides:
            ex2_stats = residual_animal_overrides["milk"]
        # Strategy 9: milk uses ESPAC directly, not literature replacement scaling.
        if strategy == 9:
            ex2_stats = None
            set_exchange("2", ["animals_total_live_weight_kg_per_kg_product"])
        elif ex2_stats is not None:
            ex2 = by_number.get("2")
            if ex2 is not None:
                milk_stats = ex2_stats
                ex2.set("meanValue", f"{float(milk_stats['mean']):.12g}")
                ex2.set("uncertaintyType", "3")
                ex2.set("minValue", f"{float(milk_stats['min']):.12g}")
                ex2.set("maxValue", f"{float(milk_stats['max']):.12g}")
        else:
            zero_exchange("2")
        ex2 = by_number.get("2")
        if ex2 is not None:
            ex2.set("name", f"product: cattle_live | summary: strategy_{strategy}")
        set_exchange("3", ["water_l_per_kg_product"])
        set_exchange("4", ["electricity_kwh_per_kg_product"])
        set_exchange("5", ["pasture_feed_kg_per_kg_product", "unmatched_pasture_feed_kg_per_kg_product"])
        set_exchange("6", ["supplement_feed_kg_per_kg_product"])
        set_exchange("7", ["area_ha_per_kg_product"])
        set_exchange("8", ["area_ha_per_kg_product"])
        set_exchange("9", ["area_ha_per_kg_product"])
        set_exchange("10", ["ch4_enteric_kg_per_kg_product"])
        set_exchange("11", ["nh3_total_kg_per_kg_product", "nh3_housing_kg_per_kg_product", "nh3_grazing_kg_per_kg_product"])
        set_exchange("12", ["nox_as_no2_kg_per_kg_product"])
        set_exchange("13", ["n2o_direct_kg_per_kg_product"])

    elif tname == "livestock00002.xml":  # meat/live
        # Avoid animal technosphere double counting: keep all animal input exchanges at zero.
        for n in ("2", "3", "4", "5"):
            zero_exchange(n)

        set_exchange("6", ["water_l_per_kg_product"])
        set_exchange("7", ["electricity_kwh_per_kg_product"])
        set_exchange("8", ["pasture_feed_kg_per_kg_product", "unmatched_pasture_feed_kg_per_kg_product"])

        # Species-specific feed datasets.
        for n in ("9", "10", "11"):
            zero_exchange(n)
        if pclass == "cattle":
            set_exchange("9", ["supplement_feed_kg_per_kg_product"])
        elif pclass == "poultry":
            set_exchange("10", ["total_feed_kg_per_kg_product"])
        elif pclass == "swine":
            set_exchange("11", ["total_feed_kg_per_kg_product"])

        set_exchange("12", ["area_ha_per_kg_product"])
        set_exchange("13", ["area_ha_per_kg_product"])
        set_exchange("14", ["area_ha_per_kg_product"])
        set_exchange("15", ["ch4_enteric_kg_per_kg_product"])
        set_exchange("16", ["nh3_total_kg_per_kg_product", "nh3_housing_kg_per_kg_product", "nh3_grazing_kg_per_kg_product"])
        set_exchange("17", ["nox_as_no2_kg_per_kg_product"])
        set_exchange("18", ["n2o_direct_kg_per_kg_product"])

    else:
        # Fallback for unknown templates: use generalComment expression parser.
        for ex in exchanges:
            og = ex.find("eco:outputGroup", NS)
            if og is not None and (og.text or "").strip() == "0":
                continue
            comment = ex.attrib.get("generalComment", "")
            tokens = parse_comment_tokens(comment)
            if not tokens:
                continue
            total = 0.0
            lows = []
            highs = []
            for t in tokens:
                total += resolve_value(t, row)
                lo, hi = resolve_unc(t, unc_row)
                if lo is not None:
                    lows.append(lo)
                if hi is not None:
                    highs.append(hi)
            ex.set("meanValue", f"{total:.12g}")
            if lows and highs:
                lo_sum = float(sum(lows))
                hi_sum = float(sum(highs))
                if hi_sum < lo_sum:
                    lo_sum, hi_sum = hi_sum, lo_sum
                if hi_sum == lo_sum:
                    eps = max(abs(total) * 1e-3, 1e-9)
                    lo_sum = total - eps
                    hi_sum = total + eps
                ex.set("minValue", f"{lo_sum:.12g}")
                ex.set("maxValue", f"{hi_sum:.12g}")
                ex.set("uncertaintyType", "3")

    # Species-specific assignment for meat template exchanges so non-concerned species stay zero.
    return tree


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate livestock V2 XML from V2 CSV outputs.")
    parser.add_argument("--lci", default="outputs/CSVs/07_product_lci_v2.csv")
    parser.add_argument("--unc", default="outputs/CSVs/07_product_lci_v2_uncertainty.csv")
    parser.add_argument("--template-dir", default="inputs")
    parser.add_argument("--outdir", default="outputs/05_xml_exports_livestock_lci_v2/summary_product")
    parser.add_argument("--limit", type=int, default=0, help="Optional row limit for quick runs (0 means all)")
    parser.add_argument("--aggregate", choices=["none", "national_product"], default="none")
    parser.add_argument("--strategy", type=int, default=2)
    parser.add_argument(
        "--harmonized-stock-v2",
        default="outputs/CSVs/07_product_lci_v2.csv",
        help="Optional V2 product table to derive class-harmonized stock intensities for strategy aggregation.",
    )
    parser.add_argument(
        "--animal-class-stock-v2",
        default="outputs/CSVs/07_animal_class_stock.csv",
        help="V2 animal class stock table used for replacement-animal strategy computations.",
    )
    parser.add_argument(
        "--coeffs-yaml",
        default="inputs/02-05_espac_lci_coefficients.yml",
        help="Coefficients YAML containing literature replacement-rate factors.",
    )
    args = parser.parse_args()

    lci = pd.read_csv(args.lci)
    if "Product" in lci.columns and "product" not in lci.columns:
        lci = lci.rename(columns={"Product": "product"})
    if "Province" in lci.columns and "ual_prov" not in lci.columns:
        lci = lci.rename(columns={"Province": "ual_prov"})
    unc = pd.read_csv(args.unc) if Path(args.unc).exists() else pd.DataFrame()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    template_dir = Path(args.template_dir)

    if args.aggregate == "national_product":
        lci = aggregate_national_product(lci)
        stock_overrides = build_stock_overrides_from_v2(Path(args.harmonized_stock_v2))
        residual_overrides = build_residual_animal_overrides_from_v2(Path(args.harmonized_stock_v2))
        replacement_overrides = build_replacement_animal_overrides_from_v2(
            Path(args.harmonized_stock_v2),
            Path(args.animal_class_stock_v2),
        )
        # Strategy 9 uses literature replacement factor only for eggs.
        if args.strategy == 9:
            replacement_overrides = build_eggs_replacement_override_from_literature(
                Path(args.harmonized_stock_v2),
                Path(args.coeffs_yaml),
                base_overrides=residual_overrides,
            )
        if stock_overrides:
            for p, v in stock_overrides.items():
                mask = lci["product"].astype(str) == str(p)
                if mask.any() and "animals_total_live_weight_kg_per_kg_product" in lci.columns:
                    lci.loc[mask, "animals_total_live_weight_kg_per_kg_product"] = float(v)
        # Keep the same product scope as the original (v1) strategy exports.
        lci = lci[lci["product"].astype(str).isin(LEGACY_STRATEGY_PRODUCTS)].copy()
        lci["process_name"] = lci["product"].astype(str).map(lambda p: f"product: {p} | summary: strategy_{args.strategy}")
    elif args.limit and args.limit > 0:
        lci = lci.head(args.limit).copy()

    written = []
    for i, r in lci.iterrows():
        template = choose_template(str(r.get("product", "")), template_dir)
        unc_row = get_unc_row(unc, r, i) if not unc.empty else None
        tree = render_xml(
            template,
            r,
            unc_row,
            residual_animal_overrides=residual_overrides if args.aggregate == "national_product" else None,
            replacement_animal_overrides=replacement_overrides if args.aggregate == "national_product" else None,
            strategy=args.strategy,
        )
        prod_slug = safe_slug(str(r.get("product", "livestock")))
        if args.aggregate == "national_product":
            name = f"product_{prod_slug}_strategy_{args.strategy}.xml"
        else:
            name = f"{i+1:05d}_product_{prod_slug}_v2.xml"
        out_path = outdir / name
        tree.write(out_path, encoding="UTF-8", xml_declaration=True)
        written.append(out_path)

    print(f"Wrote {len(written):,} livestock V2 XML files to {outdir}")
    if written:
        print(f"Sample output: {written[0]}")


if __name__ == "__main__":
    main()
