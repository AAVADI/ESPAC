"""Build a class-based livestock model (v2) from ESPAC SQLite.

Outputs four CSV tables:
- 07_animal_class_stock.csv
- 07_class_feed_intake.csv
- 07_class_direct_emissions.csv
- 07_product_lci_v2.csv
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import pandas as pd
import sqlite3
import yaml


DAYS_PER_YEAR = 365.0
EGG_OUTPUT_PERIODS_PER_YEAR = 52.0
EGG_WEIGHT_KG_PER_EGG = 0.056699
EGGS_PER_LAYER_PER_DAY_FALLBACK = 0.75

# Conservative default live weights (kg/head) to avoid confounding all classes.
CLASS_WEIGHT_DEFAULTS: Dict[str, float] = {
    "cattle_male_total": 420.0,
    "cattle_ternero": 120.0,
    "cattle_torete": 280.0,
    "cattle_toro": 650.0,
    "cattle_female_total": 400.0,
    "cattle_ternera": 110.0,
    "cattle_vacona": 300.0,
    "cattle_vaca": 500.0,
    "swine_lt2m": 18.0,
    "swine_gt2m": 80.0,
    "ovine_lt6m": 25.0,
    "ovine_gt6m": 45.0,
    "layer_hen": 1.9,
    "breeder_hen": 2.4,
    "chick": 0.9,
    "ostrich": 95.0,
    "turkey": 8.0,
    "quail": 0.18,
    "other_livestock_k1101": 60.0,
    "other_livestock_k1102": 300.0,
    "other_livestock_k1103": 120.0,
    "other_livestock_k1104": 45.0,
}

# Simple EF placeholders (kg gas/head/day); replace with calibrated factors later.
EMISSION_FACTORS: Dict[str, Dict[str, float]] = {
    "cattle": {"ch4_enteric": 0.22, "ch4_manure": 0.02, "n2o_direct": 0.0012},
    "swine": {"ch4_enteric": 0.01, "ch4_manure": 0.015, "n2o_direct": 0.0003},
    "ovine": {"ch4_enteric": 0.03, "ch4_manure": 0.004, "n2o_direct": 0.0002},
    "poultry": {"ch4_enteric": 0.0, "ch4_manure": 0.0002, "n2o_direct": 0.00003},
    "other": {"ch4_enteric": 0.02, "ch4_manure": 0.005, "n2o_direct": 0.00025},
}

# Simple resource-use defaults by species/class (used when ESPAC does not provide direct values).
WATER_L_HEAD_DAY: Dict[str, float] = {
    "cattle": 45.0,
    "swine": 7.0,
    "ovine": 7.6,
    "poultry": 0.275,
    "other": 12.0,
}
ELECTRICITY_KWH_HEAD_DAY: Dict[str, float] = {
    "cattle": 0.6,
    "swine": 0.03,
    "ovine": 0.01,
    "poultry": 0.005,
    "other": 0.01,
}
DMI_KG_HEAD_DAY: Dict[str, float] = {
    "cattle": 10.0,
    "swine": 2.2,
    "ovine": 1.2,
    "poultry": 0.068,
    "other": 2.0,
}
PASTURE_SHARE_DEFAULT: Dict[str, float] = {
    "cattle": 0.6,
    "swine": 0.0,
    "ovine": 0.8,
    "poultry": 0.0,
    "other": 0.5,
}
SUPPLEMENT_SHARE_DEFAULT: Dict[str, float] = {
    "cattle": 0.4,
    "swine": 0.7,
    "ovine": 0.2,
    "poultry": 1.0,
    "other": 0.5,
}


@dataclass
class ClassRecord:
    identificador: str
    ual_prov: str
    species: str
    product_system: str
    animal_class: str
    head_count: float
    avg_live_weight_kg: float
    days_present: float
    source_table: str
    fact_exp_fin: float


def load_coefficients(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def get_broiler_residence_days(coefficients: dict) -> float:
    return float(
        coefficients.get("livestock_residence_time_factors", {})
        .get("meat_poultry", {})
        .get("residence_days", DAYS_PER_YEAR)
    )


def _to_num(s: pd.Series) -> pd.Series:
    # Normalize locale-specific numeric text (for example, decimal comma)
    # before coercing to float.
    txt = s.astype(str).str.strip().str.replace("\u00a0", "", regex=False).str.replace(" ", "", regex=False)
    has_comma = txt.str.contains(",", regex=False, na=False)
    has_dot = txt.str.contains(".", regex=False, na=False)

    both = has_comma & has_dot
    if both.any():
        last_comma = txt.str.rfind(",")
        last_dot = txt.str.rfind(".")
        comma_decimal = both & (last_comma > last_dot)
        dot_decimal = both & ~comma_decimal
        txt.loc[comma_decimal] = (
            txt.loc[comma_decimal].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
        )
        txt.loc[dot_decimal] = txt.loc[dot_decimal].str.replace(",", "", regex=False)

    only_comma = has_comma & ~has_dot
    txt.loc[only_comma] = txt.loc[only_comma].str.replace(",", ".", regex=False)

    txt = txt.replace({"": None, "None": None, "none": None, "nan": None, "NaN": None})
    return pd.to_numeric(txt, errors="coerce").fillna(0.0)


def _to_float(value: object, default: float = 0.0) -> float:
    val = float(_to_num(pd.Series([value])).iloc[0])
    return val if pd.notna(val) else default


def _expansion_factor(row: pd.Series, default: float = 1.0) -> float:
    exp = _to_float(row.get("fact_exp_fin", default), default=default)
    return exp if exp > 0 else default



def _weighted_count(df: pd.DataFrame, col: str, exp_col: str = "fact_exp_fin") -> pd.Series:
    base = _to_num(df[col])
    exp = _to_num(df.get(exp_col, 1.0))
    exp = exp.where(exp > 0, 1.0)
    return base * exp



def build_animal_class_stock(con: sqlite3.Connection, coefficients: dict) -> pd.DataFrame:
    out: List[ClassRecord] = []
    broiler_residence_days = get_broiler_residence_days(coefficients)

    gl = pd.read_sql_query("SELECT * FROM rel_inec_glnac", con)
    gp = pd.read_sql_query("SELECT * FROM rel_inec_gpnac", con)
    gv = pd.read_sql_query("SELECT * FROM rel_inec_gvnac", con)
    ap = pd.read_sql_query("SELECT * FROM rel_inec_apnac", con)
    oe = pd.read_sql_query("SELECT * FROM rel_inec_oenac", con)

    cattle_map = [
        ("gl_totmachos_ta", "cattle_male_total"),
        ("gl_terneros_ta", "cattle_ternero"),
        ("gl_toretes_ta", "cattle_torete"),
        ("gl_toros_ta", "cattle_toro"),
        ("gl_tothembras_ta", "cattle_female_total"),
        ("gl_terneras_ta", "cattle_ternera"),
        ("gl_vaconas_ta", "cattle_vacona"),
        ("gl_vacas_ta", "cattle_vaca"),
    ]
    for col, cls in cattle_map:
        if col not in gl.columns:
            continue
        wc = _weighted_count(gl, col)
        for i, row in gl.iterrows():
            v = float(wc.iloc[i])
            if v <= 0:
                continue
            out.append(
                ClassRecord(
                    identificador=str(row["identificador"]),
                    ual_prov=str(row.get("ual_prov", "")),
                    species="cattle",
                    product_system="milk_meat_cattle",
                    animal_class=cls,
                    head_count=v,
                    avg_live_weight_kg=CLASS_WEIGHT_DEFAULTS[cls],
                    days_present=DAYS_PER_YEAR,
                    source_table="rel_inec_glnac",
                    fact_exp_fin=_expansion_factor(row),
                )
            )

    swine_map = [("gp_totanio_men2m", "swine_lt2m"), ("gp_totanio_mas2m", "swine_gt2m")]
    for col, cls in swine_map:
        if col not in gp.columns:
            continue
        wc = _weighted_count(gp, col)
        for i, row in gp.iterrows():
            v = float(wc.iloc[i])
            if v <= 0:
                continue
            out.append(ClassRecord(str(row["identificador"]), str(row.get("ual_prov", "")), "swine", "swine_meat", cls, v, CLASS_WEIGHT_DEFAULTS[cls], DAYS_PER_YEAR, "rel_inec_gpnac", _expansion_factor(row)))

    ovine_map = [("gv_ta_menosde6", "ovine_lt6m"), ("gv_ta_masde6", "ovine_gt6m")]
    for col, cls in ovine_map:
        if col not in gv.columns:
            continue
        wc = _weighted_count(gv, col)
        for i, row in gv.iterrows():
            v = float(wc.iloc[i])
            if v <= 0:
                continue
            out.append(ClassRecord(str(row["identificador"]), str(row.get("ual_prov", "")), "ovine", "ovine_meat", cls, v, CLASS_WEIGHT_DEFAULTS[cls], DAYS_PER_YEAR, "rel_inec_gvnac", _expansion_factor(row)))

    poultry_map = [
        ("ap_ctponedoras", "layer_hen"),
        ("ap_ctreproductoras", "breeder_hen"),
        ("ap_ctpollitos", "chick"),
        ("ap_ctavestruces", "ostrich"),
        ("ap_ctpavos", "turkey"),
        ("ap_ctcodornices", "quail"),
    ]
    for col, cls in poultry_map:
        if col not in ap.columns:
            continue
        wc = _weighted_count(ap, col)
        for i, row in ap.iterrows():
            v = float(wc.iloc[i])
            if v <= 0:
                continue
            system = "eggs_poultry" if cls in {"layer_hen", "breeder_hen"} else "meat_poultry"
            days_present = broiler_residence_days if cls == "chick" else DAYS_PER_YEAR
            out.append(ClassRecord(str(row["identificador"]), str(row.get("ual_prov", "")), "poultry", system, cls, v, CLASS_WEIGHT_DEFAULTS[cls], days_present, "rel_inec_apnac", _expansion_factor(row)))

    other_map = [
        ("oe_k1101", "other_livestock_k1101"),
        ("oe_k1102", "other_livestock_k1102"),
        ("oe_k1103", "other_livestock_k1103"),
        ("oe_k1104", "other_livestock_k1104"),
    ]
    for col, cls in other_map:
        if col not in oe.columns:
            continue
        wc = _weighted_count(oe, col)
        for i, row in oe.iterrows():
            v = float(wc.iloc[i])
            if v <= 0:
                continue
            out.append(ClassRecord(str(row["identificador"]), str(row.get("ual_prov", "")), "other", "other_livestock", cls, v, CLASS_WEIGHT_DEFAULTS[cls], DAYS_PER_YEAR, "rel_inec_oenac", _expansion_factor(row)))

    stock = pd.DataFrame([r.__dict__ for r in out])
    stock["total_live_weight_kg"] = stock["head_count"] * stock["avg_live_weight_kg"]
    return stock



def build_class_feed_intake(stock: pd.DataFrame, con: sqlite3.Connection) -> pd.DataFrame:
    gl = pd.read_sql_query("SELECT identificador, gl_porc_pasto, gl_porc_sobrealimento FROM rel_inec_glnac", con)
    gp = pd.read_sql_query("SELECT identificador, gp_porc_alimento, gp_porc_sobrealimentacion, gp_porc_desechos FROM rel_inec_gpnac", con)
    ap = pd.read_sql_query("SELECT identificador, ap_cons_gapo, ap_cons_gare, ap_cons_polli, ap_cons_avest, ap_cons_pavos, ap_cons_codor FROM rel_inec_apnac", con)

    rows = []
    for _, r in stock.iterrows():
        rec = {
            "identificador": r["identificador"],
            "ual_prov": r.get("ual_prov", ""),
            "species": r["species"],
            "animal_class": r["animal_class"],
            "head_count": r["head_count"],
            "feed_pasture_share_pct": None,
            "feed_supplement_share_pct": None,
            "feed_waste_share_pct": None,
            "feed_kg_asfed_head_day": None,
            "feed_data_quality": "proxy_or_missing",
        }

        if r["species"] == "cattle":
            m = gl[gl["identificador"].astype(str) == str(r["identificador"])]
            if not m.empty:
                rec["feed_pasture_share_pct"] = float(_to_num(m["gl_porc_pasto"]).iloc[0])
                rec["feed_supplement_share_pct"] = float(_to_num(m["gl_porc_sobrealimento"]).iloc[0])
                rec["feed_data_quality"] = "espac_share"

        elif r["species"] == "swine":
            m = gp[gp["identificador"].astype(str) == str(r["identificador"])]
            if not m.empty:
                rec["feed_supplement_share_pct"] = float(_to_num(m["gp_porc_alimento"]).iloc[0])
                rec["feed_pasture_share_pct"] = float(_to_num(m["gp_porc_sobrealimentacion"]).iloc[0])
                rec["feed_waste_share_pct"] = float(_to_num(m["gp_porc_desechos"]).iloc[0])
                rec["feed_data_quality"] = "espac_share"

        elif r["species"] == "poultry":
            m = ap[ap["identificador"].astype(str) == str(r["identificador"])]
            if not m.empty:
                col_map = {
                    "layer_hen": "ap_cons_gapo",
                    "breeder_hen": "ap_cons_gare",
                    "chick": "ap_cons_polli",
                    "ostrich": "ap_cons_avest",
                    "turkey": "ap_cons_pavos",
                    "quail": "ap_cons_codor",
                }
                c = col_map.get(r["animal_class"])
                if c in m.columns:
                    rec["feed_kg_asfed_head_day"] = float(_to_num(m[c]).iloc[0])
                    rec["feed_data_quality"] = "espac_absolute"

        rows.append(rec)

    return pd.DataFrame(rows)



def build_class_direct_emissions(stock: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in stock.iterrows():
        ef = EMISSION_FACTORS.get(r["species"], EMISSION_FACTORS["other"])
        ch4e = r["head_count"] * r["days_present"] * ef["ch4_enteric"]
        ch4m = r["head_count"] * r["days_present"] * ef["ch4_manure"]
        n2od = r["head_count"] * r["days_present"] * ef["n2o_direct"]
        rows.append(
            {
                "identificador": r["identificador"],
                "ual_prov": r.get("ual_prov", ""),
                "species": r["species"],
                "animal_class": r["animal_class"],
                "head_count": r["head_count"],
                "days_present": r["days_present"],
                "ch4_enteric_kg_year": ch4e,
                "ch4_manure_kg_year": ch4m,
                "n2o_direct_kg_year": n2od,
                "emissions_note": "placeholder daily EFs; replace with tier-2 or region-calibrated factors",
            }
        )
    return pd.DataFrame(rows)



def build_product_lci_v2(stock: pd.DataFrame, emissions: pd.DataFrame, con: sqlite3.Connection) -> pd.DataFrame:
    gl = pd.read_sql_query(
        "SELECT identificador, ual_prov, gl_litlecvacaje, gl_litlecven, vacas_ordenadas, litros_orde_ados, gl_vacas_ta, "
        "gl_propleche, gl_propdoblep, gl_propcarne, fact_exp_fin "
        "FROM rel_inec_glnac",
        con,
    )
    ap = pd.read_sql_query(
        "SELECT identificador, ual_prov, ap_venta_hcodor, ap_prod_hcodor, avesp_ventas, ap_ctponedoras, ap_k1221, fact_exp_fin, "
        "ap_vengapo, ap_vengarep, ap_venpoypo, ap_venavest, ap_venpavos, ap_vencodorn "
        "FROM rel_inec_apnac",
        con,
    )

    cattle_system_map: dict[str, str] = {}
    for _, row in gl.iterrows():
        milk_flag = float(_to_num(pd.Series([row.get("gl_propleche", 0)])).iloc[0])
        dual_flag = float(_to_num(pd.Series([row.get("gl_propdoblep", 0)])).iloc[0])
        beef_flag = float(_to_num(pd.Series([row.get("gl_propcarne", 0)])).iloc[0])
        system = "(unknown)"
        if milk_flag > 0:
            system = "dairy"
        elif dual_flag > 0:
            system = "dual-purpose"
        elif beef_flag > 0:
            system = "beef"
        cattle_system_map[str(row["identificador"])] = system

    poultry_system_map: dict[str, str] = {}
    for _, row in ap.iterrows():
        activity = str(row.get("ap_k1221", "") or "").strip().lower()
        if "huevo" in activity:
            system = "layers"
        elif "doble" in activity:
            system = "dual-purpose poultry"
        else:
            system = "(unknown)"
        poultry_system_map[str(row["identificador"])] = system

    farm_lw = stock.groupby("identificador", as_index=False)["total_live_weight_kg"].sum()
    stock_species = (
        stock.assign(animal_days=stock["head_count"] * stock["days_present"])
        .groupby(["identificador", "species"], as_index=False)
        .agg(
            head_count=("head_count", "sum"),
            animal_days=("animal_days", "sum"),
            total_live_weight_kg=("total_live_weight_kg", "sum"),
        )
    )
    em_species = (
        emissions.groupby(["identificador", "species"], as_index=False)[["ch4_enteric_kg_year", "ch4_manure_kg_year", "n2o_direct_kg_year"]]
        .sum()
    )
    farm_animal_days = stock.assign(animal_days=stock["head_count"] * stock["days_present"]).groupby("identificador", as_index=False)["animal_days"].sum()
    farm_area_ha = pd.concat(
        [
            pd.read_sql_query("SELECT identificador, gl_supcrianza_ha AS area_ha FROM rel_inec_glnac", con),
            pd.read_sql_query("SELECT identificador, gp_superficie_ha AS area_ha FROM rel_inec_gpnac", con),
            pd.read_sql_query("SELECT identificador, gv_superficie_ha AS area_ha FROM rel_inec_gvnac", con),
            pd.read_sql_query("SELECT identificador, oe_superficie_ha AS area_ha FROM rel_inec_oenac", con),
        ],
        ignore_index=True,
    )
    farm_area_ha["area_ha"] = pd.to_numeric(farm_area_ha["area_ha"], errors="coerce").fillna(0.0)
    farm_area_ha = farm_area_ha.groupby("identificador", as_index=False)["area_ha"].sum()

    rows = []

    for _, r in gl.iterrows():
        fid = str(r["identificador"])
        milk_l = float(_to_num(pd.Series([r.get("gl_litlecvacaje", 0)])).iloc[0])
        if milk_l <= 0:
            milk_l = float(_to_num(pd.Series([r.get("litros_orde_ados", 0)])).iloc[0])
        exp = _expansion_factor(r)
        # ESPAC milk in this pathway is daily-scale; annualize to keep all
        # per-kg intensities on a year-consistent denominator.
        milk_kg_year = milk_l * DAYS_PER_YEAR * exp
        if milk_kg_year <= 0:
            continue
        lw = farm_lw[farm_lw["identificador"] == fid]
        ad_farm = farm_animal_days[farm_animal_days["identificador"] == fid]
        ad_cattle = stock_species[(stock_species["identificador"].astype(str) == fid) & (stock_species["species"] == "cattle")]
        area = farm_area_ha[farm_area_ha["identificador"].astype(str) == fid]
        farm_days = float(ad_farm["animal_days"].iloc[0]) if not ad_farm.empty else 0.0
        cattle_days_total = float(ad_cattle["animal_days"].iloc[0]) if not ad_cattle.empty else 0.0
        area_farm_ha = float(area["area_ha"].iloc[0]) if not area.empty else 0.0

        # Product-specific herd attribution: milk uses milking cows (or adult cows fallback).
        milking_heads = float(_to_num(pd.Series([r.get("vacas_ordenadas", 0)])).iloc[0]) * exp
        if milking_heads <= 0:
            milking_heads = float(_to_num(pd.Series([r.get("gl_vacas_ta", 0)])).iloc[0]) * exp
        if milking_heads <= 0:
            continue
        animal_days = milking_heads * DAYS_PER_YEAR
        # Allocate farm area by product-specific animal-day share.
        area_share = (animal_days / farm_days) if farm_days > 0 else 0.0
        area_share = min(max(area_share, 0.0), 1.0)
        area_ha = area_farm_ha * area_share

        ef = EMISSION_FACTORS["cattle"]
        ch4_enteric_total = animal_days * ef["ch4_enteric"]
        ch4_manure_total = animal_days * ef["ch4_manure"]
        n2o_direct_total = animal_days * ef["n2o_direct"]
        total_ghg = ch4_enteric_total + ch4_manure_total + n2o_direct_total
        water_total = animal_days * WATER_L_HEAD_DAY["cattle"]
        elec_total = animal_days * ELECTRICITY_KWH_HEAD_DAY["cattle"]
        dmi_total = animal_days * DMI_KG_HEAD_DAY["cattle"]
        pasture_total = dmi_total * PASTURE_SHARE_DEFAULT["cattle"]
        supp_total = dmi_total * SUPPLEMENT_SHARE_DEFAULT["cattle"]
        unmatched_pasture_total = pasture_total * 0.15
        nh3_total = n2o_direct_total * 2.2
        nh3_housing = nh3_total * 0.7
        nh3_grazing = nh3_total * 0.3
        nox_as_no2 = n2o_direct_total * 0.4
        attributed_live_weight = milking_heads * CLASS_WEIGHT_DEFAULTS["cattle_vaca"]
        rows.append({
            "identificador": fid,
            "ual_prov": str(r.get("ual_prov", "")),
            "product": "milk",
            "System": cattle_system_map.get(fid, "(unknown)"),
            "product_output_kg_year": milk_kg_year,
            "allocation_rule": "farm-total / milk-output (temporary)",
            "ch4_enteric_kg_per_kg_product": ch4_enteric_total / milk_kg_year,
            "ch4_manure_kg_per_kg_product": ch4_manure_total / milk_kg_year,
            "n2o_direct_kg_per_kg_product": n2o_direct_total / milk_kg_year,
            "total_direct_gas_kg_per_kg_product": total_ghg / milk_kg_year,
            "water_l_per_kg_product": water_total / milk_kg_year,
            "electricity_kwh_per_kg_product": elec_total / milk_kg_year,
            "area_ha_per_kg_product": area_ha / milk_kg_year,
            "total_feed_kg_per_kg_product": dmi_total / milk_kg_year,
            "supplement_feed_kg_per_kg_product": supp_total / milk_kg_year,
            "pasture_feed_kg_per_kg_product": pasture_total / milk_kg_year,
            "unmatched_pasture_feed_kg_per_kg_product": unmatched_pasture_total / milk_kg_year,
            "nh3_total_kg_per_kg_product": nh3_total / milk_kg_year,
            "nh3_housing_kg_per_kg_product": nh3_housing / milk_kg_year,
            "nh3_grazing_kg_per_kg_product": nh3_grazing / milk_kg_year,
            "nox_as_no2_kg_per_kg_product": nox_as_no2 / milk_kg_year,
            "animals_total_live_weight_kg_per_kg_product": attributed_live_weight / milk_kg_year,
            "farm_total_live_weight_kg": float(lw["total_live_weight_kg"].iloc[0]) if not lw.empty else 0.0,
            "attributed_live_weight_kg": attributed_live_weight,
            "attribution_basis": "milking_cows",
        })

    for _, r in ap.iterrows():
        fid = str(r["identificador"])
        eggs_prod = float(_to_num(pd.Series([r.get("ap_prod_hcodor", 0)])).iloc[0])
        eggs_sale = float(_to_num(pd.Series([r.get("ap_venta_hcodor", 0)])).iloc[0])
        eggs = eggs_prod if eggs_prod > 0 else eggs_sale
        exp = _expansion_factor(r)
        lw = farm_lw[farm_lw["identificador"] == fid]
        ad_farm = farm_animal_days[farm_animal_days["identificador"] == fid]
        area = farm_area_ha[farm_area_ha["identificador"].astype(str) == fid]
        farm_days = float(ad_farm["animal_days"].iloc[0]) if not ad_farm.empty else 0.0
        area_farm_ha = float(area["area_ha"].iloc[0]) if not area.empty else 0.0

        layer_heads = float(_to_num(pd.Series([r.get("ap_ctponedoras", 0)])).iloc[0]) * exp
        if layer_heads <= 0:
            continue
        if eggs > 0:
            # ESPAC reported periods are treated as weekly counts.
            eggs_kg_year = eggs * EGG_WEIGHT_KG_PER_EGG * EGG_OUTPUT_PERIODS_PER_YEAR * exp
            egg_output_basis = "espac_weekly_output"
        else:
            # Fallback for sparse/non-numeric output fields: infer annual output
            # from layer heads and a conservative laying-rate assumption.
            eggs_kg_year = layer_heads * DAYS_PER_YEAR * EGGS_PER_LAYER_PER_DAY_FALLBACK * EGG_WEIGHT_KG_PER_EGG
            egg_output_basis = "layer_heads_fallback"
        if eggs_kg_year <= 0:
            continue
        animal_days = layer_heads * DAYS_PER_YEAR
        area_share = (animal_days / farm_days) if farm_days > 0 else 0.0
        area_share = min(max(area_share, 0.0), 1.0)
        area_ha = area_farm_ha * area_share

        ef = EMISSION_FACTORS["poultry"]
        ch4_enteric_total = animal_days * ef["ch4_enteric"]
        ch4_manure_total = animal_days * ef["ch4_manure"]
        n2o_direct_total = animal_days * ef["n2o_direct"]
        total_ghg = ch4_enteric_total + ch4_manure_total + n2o_direct_total
        water_total = animal_days * WATER_L_HEAD_DAY["poultry"]
        elec_total = animal_days * ELECTRICITY_KWH_HEAD_DAY["poultry"]
        dmi_total = animal_days * DMI_KG_HEAD_DAY["poultry"]
        pasture_total = dmi_total * PASTURE_SHARE_DEFAULT["poultry"]
        supp_total = dmi_total * SUPPLEMENT_SHARE_DEFAULT["poultry"]
        unmatched_pasture_total = pasture_total * 0.15
        nh3_total = n2o_direct_total * 2.2
        nh3_housing = nh3_total * 0.7
        nh3_grazing = nh3_total * 0.3
        nox_as_no2 = n2o_direct_total * 0.4
        attributed_live_weight = layer_heads * CLASS_WEIGHT_DEFAULTS["layer_hen"]
        rows.append({
            "identificador": fid,
            "ual_prov": str(r.get("ual_prov", "")),
            "product": "eggs",
            "System": poultry_system_map.get(fid, "(unknown)"),
            "product_output_kg_year": eggs_kg_year,
            "allocation_rule": f"farm-total / egg-output (temporary; basis={egg_output_basis})",
            "ch4_enteric_kg_per_kg_product": ch4_enteric_total / eggs_kg_year,
            "ch4_manure_kg_per_kg_product": ch4_manure_total / eggs_kg_year,
            "n2o_direct_kg_per_kg_product": n2o_direct_total / eggs_kg_year,
            "total_direct_gas_kg_per_kg_product": total_ghg / eggs_kg_year,
            "water_l_per_kg_product": water_total / eggs_kg_year,
            "electricity_kwh_per_kg_product": elec_total / eggs_kg_year,
            "area_ha_per_kg_product": area_ha / eggs_kg_year,
            "total_feed_kg_per_kg_product": dmi_total / eggs_kg_year,
            "supplement_feed_kg_per_kg_product": supp_total / eggs_kg_year,
            "pasture_feed_kg_per_kg_product": pasture_total / eggs_kg_year,
            "unmatched_pasture_feed_kg_per_kg_product": unmatched_pasture_total / eggs_kg_year,
            "nh3_total_kg_per_kg_product": nh3_total / eggs_kg_year,
            "nh3_housing_kg_per_kg_product": nh3_housing / eggs_kg_year,
            "nh3_grazing_kg_per_kg_product": nh3_grazing / eggs_kg_year,
            "nox_as_no2_kg_per_kg_product": nox_as_no2 / eggs_kg_year,
            "animals_total_live_weight_kg_per_kg_product": attributed_live_weight / eggs_kg_year,
            "farm_total_live_weight_kg": float(lw["total_live_weight_kg"].iloc[0]) if not lw.empty else 0.0,
            "attributed_live_weight_kg": attributed_live_weight,
            "attribution_basis": "layer_hens",
        })

    # Add non-milk/non-egg livestock product proxies so all livestock systems are represented.
    # These are farm-level species outputs with explicit proxy basis to avoid silent omission.
    species_to_product = {
        # Livestock processes are expressed per kg live weight in this pipeline.
        # Therefore, no carcass-yield conversion is applied in denominators.
        "cattle": ("cattle_meat", 1.00),
        "swine": ("swine_live", 1.00),
        "ovine": ("ovine_live", 1.00),
        "poultry": ("meat_poultry", 1.00),
        "other": ("other_livestock_live", 1.00),
    }
    species_groups = stock.groupby(["identificador", "ual_prov", "species"], as_index=False).agg(
        head_count=("head_count", "sum"),
        total_live_weight_kg=("total_live_weight_kg", "sum"),
    )
    for _, srow in species_groups.iterrows():
        species = str(srow["species"])
        if species not in species_to_product:
            continue
        product_name, yield_proxy = species_to_product[species]

        fid = str(srow["identificador"])
        em = em_species[(em_species["identificador"].astype(str) == fid) & (em_species["species"] == species)]
        ad = stock_species[(stock_species["identificador"].astype(str) == fid) & (stock_species["species"] == species)]
        ad_farm = farm_animal_days[farm_animal_days["identificador"] == fid]
        area = farm_area_ha[farm_area_ha["identificador"].astype(str) == fid]
        if em.empty:
            continue

        # Keep denominator herd-based for consistency with herd-based resource/emission numerators.
        product_output_kg_year = float(srow["total_live_weight_kg"]) * float(yield_proxy)
        if product_output_kg_year <= 0:
            continue

        animal_days = float(ad["animal_days"].iloc[0]) if not ad.empty else 0.0
        farm_days = float(ad_farm["animal_days"].iloc[0]) if not ad_farm.empty else 0.0
        area_farm_ha = float(area["area_ha"].iloc[0]) if not area.empty else 0.0
        area_share = (animal_days / farm_days) if farm_days > 0 else 0.0
        area_share = min(max(area_share, 0.0), 1.0)
        area_ha = area_farm_ha * area_share
        total_ghg = float(em[["ch4_enteric_kg_year", "ch4_manure_kg_year", "n2o_direct_kg_year"]].sum(axis=1).iloc[0])

        water_total = animal_days * WATER_L_HEAD_DAY.get(species, WATER_L_HEAD_DAY["other"])
        elec_total = animal_days * ELECTRICITY_KWH_HEAD_DAY.get(species, ELECTRICITY_KWH_HEAD_DAY["other"])
        dmi_total = animal_days * DMI_KG_HEAD_DAY.get(species, DMI_KG_HEAD_DAY["other"])
        pasture_total = dmi_total * PASTURE_SHARE_DEFAULT.get(species, PASTURE_SHARE_DEFAULT["other"])
        supp_total = dmi_total * SUPPLEMENT_SHARE_DEFAULT.get(species, SUPPLEMENT_SHARE_DEFAULT["other"])
        unmatched_pasture_total = pasture_total * 0.15
        nh3_total = float(em["n2o_direct_kg_year"].iloc[0]) * 2.2
        nh3_housing = nh3_total * 0.7
        nh3_grazing = nh3_total * 0.3
        nox_as_no2 = float(em["n2o_direct_kg_year"].iloc[0]) * 0.4

        rows.append({
            "identificador": fid,
            "ual_prov": str(srow.get("ual_prov", "")),
            "product": product_name,
            "System": (
                cattle_system_map.get(fid, "(unknown)") if product_name == "cattle_meat"
                else "(all swine)" if product_name == "swine_live"
                else "(all ovine)" if product_name == "ovine_live"
                else "(all holdings)"
            ),
            "product_output_kg_year": product_output_kg_year,
            "allocation_rule": "farm-total / species-output proxy (temporary)",
            "ch4_enteric_kg_per_kg_product": float(em["ch4_enteric_kg_year"].iloc[0]) / product_output_kg_year,
            "ch4_manure_kg_per_kg_product": float(em["ch4_manure_kg_year"].iloc[0]) / product_output_kg_year,
            "n2o_direct_kg_per_kg_product": float(em["n2o_direct_kg_year"].iloc[0]) / product_output_kg_year,
            "total_direct_gas_kg_per_kg_product": total_ghg / product_output_kg_year,
            "water_l_per_kg_product": water_total / product_output_kg_year,
            "electricity_kwh_per_kg_product": elec_total / product_output_kg_year,
            "area_ha_per_kg_product": area_ha / product_output_kg_year,
            "total_feed_kg_per_kg_product": dmi_total / product_output_kg_year,
            "supplement_feed_kg_per_kg_product": supp_total / product_output_kg_year,
            "pasture_feed_kg_per_kg_product": pasture_total / product_output_kg_year,
            "unmatched_pasture_feed_kg_per_kg_product": unmatched_pasture_total / product_output_kg_year,
            "nh3_total_kg_per_kg_product": nh3_total / product_output_kg_year,
            "nh3_housing_kg_per_kg_product": nh3_housing / product_output_kg_year,
            "nh3_grazing_kg_per_kg_product": nh3_grazing / product_output_kg_year,
            "nox_as_no2_kg_per_kg_product": nox_as_no2 / product_output_kg_year,
            "animals_total_live_weight_kg_per_kg_product": float(srow["total_live_weight_kg"]) / product_output_kg_year,
            "farm_total_live_weight_kg": float(srow["total_live_weight_kg"]),
        })

    return pd.DataFrame(rows)


def apply_v1_common_sense_calibration(
    product_df: pd.DataFrame,
    v1_reference_csv: Path,
) -> pd.DataFrame:
    """
    Calibrate V2 per-kg intensities to V1 product-level medians.
    This preserves V2 row-level structure while anchoring magnitudes to validated ranges.
    """
    if product_df.empty or not v1_reference_csv.exists():
        return product_df

    v1 = pd.read_csv(v1_reference_csv)
    if "Product" not in v1.columns:
        return product_df

    map_product = {
        "cattle_meat": "cattle_live",
        "swine_live": "swine_live",
        "ovine_live": "ovine_live",
        "meat_poultry": "meat_poultry",
        "eggs": "eggs",
        "milk": "milk",
        "other_livestock_live": None,
    }
    col_map = {
        "animals_total_live_weight_kg_per_kg_product": "Animals_total_live_weight_kg_per_1kg_product",
        "water_l_per_kg_product": "Water_l_per_1kg_product",
        "electricity_kwh_per_kg_product": "Electricity_kWh_per_1kg_product",
        "total_feed_kg_per_kg_product": "Total_feed_kg_per_1kg_product",
        "supplement_feed_kg_per_kg_product": "Supplement_feed_kg_per_1kg_product",
        "pasture_feed_kg_per_kg_product": "Pasture_feed_kg_per_1kg_product",
        "unmatched_pasture_feed_kg_per_kg_product": "Unmatched_pasture_feed_kg_per_1kg_product",
        "area_ha_per_kg_product": "Area_ha_per_1kg_product",
        "ch4_enteric_kg_per_kg_product": "kgCH4_livestock_total_per_1kg_product",
        "nh3_total_kg_per_kg_product": "kgNH3_manure_mgmt_total_per_1kg_product",
        "nh3_housing_kg_per_kg_product": "kgNH3_manure_housing_storage_yard_per_1kg_product",
        "nh3_grazing_kg_per_kg_product": "kgNH3_grazing_per_1kg_product",
        "nox_as_no2_kg_per_kg_product": "kgNOx_manure_mgmt_as_NO2_per_1kg_product",
        "n2o_direct_kg_per_kg_product": "kgN2O_manure_mgmt_total_per_1kg_product",
    }

    out = product_df.copy()
    for p in out["product"].dropna().unique():
        p_ref = map_product.get(str(p))
        if not p_ref:
            continue
        ref_rows = v1[v1["Product"].astype(str) == str(p_ref)]
        if ref_rows.empty:
            continue
        ref_med = ref_rows.median(numeric_only=True)
        v2_rows = out[out["product"].astype(str) == str(p)]
        v2_med = v2_rows.median(numeric_only=True)

        for v2_col, v1_col in col_map.items():
            if v2_col not in out.columns or v1_col not in ref_med.index or v2_col not in v2_med.index:
                continue
            ref_val = float(ref_med.get(v1_col, 0.0) or 0.0)
            cur_val = float(v2_med.get(v2_col, 0.0) or 0.0)
            if ref_val <= 0 or cur_val <= 0:
                continue
            factor = ref_val / cur_val
            # Avoid pathological scaling jumps while still correcting large drifts.
            factor = max(min(factor, 1000.0), 0.001)
            mask = out["product"].astype(str) == str(p)
            out.loc[mask, v2_col] = pd.to_numeric(out.loc[mask, v2_col], errors="coerce").fillna(0.0) * factor

    return out


def summarize_with_uncertainty(df: pd.DataFrame, group_cols: List[str], value_cols: List[str], scope_name: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    g = df.groupby(group_cols, dropna=False)
    rows = []
    for keys, part in g:
        if not isinstance(keys, tuple):
            keys = (keys,)
        base = {c: k for c, k in zip(group_cols, keys)}
        base["scope"] = scope_name
        base["n_records"] = int(len(part))
        for c in value_cols:
            s = pd.to_numeric(part[c], errors="coerce").dropna()
            if s.empty:
                continue
            base[f"{c}__median"] = float(s.median())
            base[f"{c}__p05"] = float(s.quantile(0.05))
            base[f"{c}__p95"] = float(s.quantile(0.95))
            base[f"{c}__min"] = float(s.min())
            base[f"{c}__max"] = float(s.max())
        rows.append(base)
    return pd.DataFrame(rows)



def main() -> None:
    parser = argparse.ArgumentParser(description="Build ESPAC livestock class-based model tables.")
    parser.add_argument("--db", default="outputs/01_espac_2024.sqlite", help="Path to ESPAC SQLite database")
    parser.add_argument("--outdir", default="outputs/CSVs", help="Output directory")
    parser.add_argument(
        "--coefficients",
        default="inputs/02-05_espac_lci_coefficients.yml",
        help="Path to YAML coefficients/configuration file",
    )
    parser.add_argument(
        "--v1-reference",
        default="outputs/CSVs/03-05_espac_livestock_lci_table_filtered_dfe__summary_national.csv",
        help="Legacy national CSV used only for optional calibration of V2 magnitudes",
    )
    parser.add_argument(
        "--apply-v1-calibration",
        action="store_true",
        help="Apply optional V1 median scaling (disabled by default; upstream allocation is preferred).",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    coefficients = load_coefficients(Path(args.coefficients))

    con = sqlite3.connect(db_path)
    try:
        stock = build_animal_class_stock(con, coefficients)
        feed = build_class_feed_intake(stock, con)
        emissions = build_class_direct_emissions(stock)
        product = build_product_lci_v2(stock, emissions, con)
    finally:
        con.close()

    if args.apply_v1_calibration:
        product = apply_v1_common_sense_calibration(product, Path(args.v1_reference))

    stock.to_csv(outdir / "07_animal_class_stock.csv", index=False)
    feed.to_csv(outdir / "07_class_feed_intake.csv", index=False)
    emissions.to_csv(outdir / "07_class_direct_emissions.csv", index=False)
    product.to_csv(outdir / "07_product_lci_v2.csv", index=False)

    product_numeric = [c for c in product.columns if pd.api.types.is_numeric_dtype(product[c])]
    summary_national = summarize_with_uncertainty(product, ["product"], product_numeric, "national")
    summary_province = summarize_with_uncertainty(product, ["ual_prov", "product"], product_numeric, "province")
    product_unc = pd.concat([summary_national, summary_province], ignore_index=True, sort=False)
    product_unc.to_csv(outdir / "07_product_lci_v2_uncertainty.csv", index=False)

    print(f"Saved {len(stock):,} rows: {outdir / '07_animal_class_stock.csv'}")
    print(f"Saved {len(feed):,} rows: {outdir / '07_class_feed_intake.csv'}")
    print(f"Saved {len(emissions):,} rows: {outdir / '07_class_direct_emissions.csv'}")
    print(f"Saved {len(product):,} rows: {outdir / '07_product_lci_v2.csv'}")
    print(f"Saved {len(product_unc):,} rows: {outdir / '07_product_lci_v2_uncertainty.csv'}")


if __name__ == "__main__":
    main()
