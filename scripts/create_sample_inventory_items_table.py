from __future__ import annotations

from pathlib import Path

import pandas as pd

from crop_groups import infer_crop_group_row


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CROP_DFE_PATH = PROJECT_ROOT / "outputs" / "CSVs" / "03-05_espac_crop_lci_table_filtered_dfe__summary_crop_national.csv"
LIVESTOCK_DFE_PATH = PROJECT_ROOT / "outputs" / "CSVs" / "03-05_espac_livestock_lci_table_filtered_dfe__summary_national.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "reports"
OUTPUT_CSV = OUTPUT_DIR / "sample_inventory_items_table.csv"
OUTPUT_MD = OUTPUT_DIR / "sample_inventory_items_table.md"

CROP_GROUP_ORDER = [
    "cereals",
    "forages_pastures",
    "fruits",
    "industrial_cash",
    "pulses_oilseeds",
    "roots_tubers",
    "vegetables",
]

LIVESTOCK_PRODUCT_MAP = {
    "milk": "milk",
    "eggs": "eggs",
    "swine": "swine_live",
    "poultry": "meat_poultry",
    "beef": "cattle_live",
}


CROP_ITEM_COLUMNS = {
    "Irrig_m3": "irrigation water",
    "Fuel_ha": "fuel",
    "NPK_kgha": "NPK fertilizer",
    "AN_kgha": "N fertilizer (AN)",
    "AP_kgha": "P fertilizer (AP)",
    "AS_kgha": "K fertilizer (AS)",
    "Total_fert_min_kgha": "mineral fertilizers",
    "Total_fert_org_kgha": "organic fertilizers",
    "Seed_kgha": "seeds/planting material",
    "Organic_estiercol_kgha": "manure",
    "Organic_fermentado_kgha": "fermented organic fertilizer",
    "Organic_liquido_kgha": "liquid organic fertilizer",
    "kgNH3N_ha": "ammonia emissions",
    "kgNOxN_ha": "NOx emissions",
    "kgNO3N_ha": "nitrate emissions",
    "kgN2ON_ha": "N2O-N emissions",
    "kgCO2_fert_ha": "CO2 emissions from fertilization",
    "kgP_total": "phosphorus emissions",
    "Cd_kg_ha": "cadmium emissions",
    "Cu_kg_ha": "copper emissions",
    "Zn_kg_ha": "zinc emissions",
    "Pb_kg_ha": "lead emissions",
    "Ni_kg_ha": "nickel emissions",
    "Cr_kg_ha": "chromium emissions",
    "Hg_kg_ha": "mercury emissions",
    "SOC_mean_rate_kgChayr": "soil carbon stock change",
}


LIVESTOCK_ITEM_COLUMNS = {
    "Water_l_per_1kg_product": "water",
    "Electricity_kWh_per_1kg_product": "electricity",
    "Total_feed_kg_per_1kg_product": "feed",
    "Pasture_feed_kg_per_1kg_product": "pasture feed",
    "Supplement_feed_kg_per_1kg_product": "supplement feed",
    "Common_feed_kg_per_1kg_product": "compound/common feed",
    "Waste_feed_kg_per_1kg_product": "waste/byproduct feed",
    "kgCH4_livestock_total_per_1kg_product": "methane emissions",
    "kgNH3_manure_mgmt_total_per_1kg_product": "ammonia emissions",
    "kgNOx_manure_mgmt_as_NO2_per_1kg_product": "NOx emissions",
    "kgN2O_manure_mgmt_total_per_1kg_product": "N2O emissions",
    "kgN2ON_manure_mgmt_total_per_1kg_product": "N2O-N emissions",
}


TRACE_ELEMENT_LABEL = "trace element emissions"
HEAVY_METAL_EMISSION_LABELS = {
    "cadmium emissions",
    "chromium emissions",
    "copper emissions",
    "lead emissions",
    "mercury emissions",
    "nickel emissions",
    "zinc emissions",
}


def _is_positive(value: object) -> bool:
    num = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(num):
        return False
    return float(num) > 0


def _collapse_heavy_metal_labels(items: list[str]) -> list[str]:
    out = [x for x in items if x not in HEAVY_METAL_EMISSION_LABELS]
    has_heavy_metal = any(x in HEAVY_METAL_EMISSION_LABELS for x in items)
    if has_heavy_metal:
        out.append(TRACE_ELEMENT_LABEL)
    return sorted(set(out))


def _build_crop_items(row: pd.Series) -> list[str]:
    items: list[str] = []

    # Requested collapse: all pesticide emissions to all compartments as one item.
    if any(
        _is_positive(row.get(col))
        for col in ["Total_pesticides_kgha", "Insecticide_kgha", "Herbicide_kgha", "Fungicide_kgha"]
    ):
        items.append("pesticide emissions")

    for col, label in CROP_ITEM_COLUMNS.items():
        if _is_positive(row.get(col)):
            items.append(label)

    return _collapse_heavy_metal_labels(items)


def _build_livestock_items(row: pd.Series) -> list[str]:
    items: list[str] = []
    for col, label in LIVESTOCK_ITEM_COLUMNS.items():
        if _is_positive(row.get(col)):
            items.append(label)
    return _collapse_heavy_metal_labels(items)


def _select_crop_examples(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["crop_group"] = work.apply(
        lambda r: infer_crop_group_row(r.get("Crop", ""), r.get("Category", ""), r.get("Packaging_type2", "")),
        axis=1,
    )
    work["count"] = pd.to_numeric(work.get("count"), errors="coerce").fillna(0)

    selected_rows = []
    for group in CROP_GROUP_ORDER:
        subset = work[work["crop_group"] == group]
        if subset.empty:
            continue
        chosen = subset.sort_values("count", ascending=False).iloc[0]
        selected_rows.append(
            {
                "system": "crop",
                "sample_key": group,
                "product": chosen["Crop"],
                "data_points": int(chosen["count"]),
                "inventory_items_considered": "; ".join(_build_crop_items(chosen)),
            }
        )

    return pd.DataFrame(selected_rows)


def _select_livestock_examples(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["count"] = pd.to_numeric(work.get("count"), errors="coerce").fillna(0)

    selected_rows = []
    for key, product_name in LIVESTOCK_PRODUCT_MAP.items():
        subset = work[work["Product"] == product_name]
        if subset.empty:
            continue
        chosen = subset.sort_values("count", ascending=False).iloc[0]
        selected_rows.append(
            {
                "system": "livestock",
                "sample_key": key,
                "product": chosen["Product"],
                "data_points": int(chosen["count"]),
                "inventory_items_considered": "; ".join(_build_livestock_items(chosen)),
            }
        )

    return pd.DataFrame(selected_rows)


def _write_markdown(df: pd.DataFrame, path: Path) -> None:
    lines = [
        "# Sample inventory items table",
        "",
        "One representative product per crop group plus milk, eggs, swine, poultry, and beef.",
        "",
        "| system | sample_key | product | data_points | inventory_items_considered |",
        "|---|---|---|---:|---|",
    ]
    for row in df.itertuples(index=False):
        lines.append(
            f"| {row.system} | {row.sample_key} | {row.product} | {row.data_points} | {row.inventory_items_considered} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    crop_df = pd.read_csv(CROP_DFE_PATH)
    livestock_df = pd.read_csv(LIVESTOCK_DFE_PATH)

    crop_samples = _select_crop_examples(crop_df)
    livestock_samples = _select_livestock_examples(livestock_df)

    out = pd.concat([crop_samples, livestock_samples], ignore_index=True)
    out = out.sort_values(["system", "sample_key"], kind="stable").reset_index(drop=True)

    out.to_csv(OUTPUT_CSV, index=False)
    _write_markdown(out, OUTPUT_MD)

    print(f"Sample table CSV saved to: {OUTPUT_CSV}")
    print(f"Sample table Markdown saved to: {OUTPUT_MD}")
    print(f"Rows exported: {len(out)}")


if __name__ == "__main__":
    main()
