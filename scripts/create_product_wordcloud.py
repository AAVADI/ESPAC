from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd
from wordcloud import WordCloud


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CROP_SUMMARY_PATH = PROJECT_ROOT / "outputs" / "CSVs" / "02_espac_crop_lci_table_filtered__summary_crop_national.csv"
LIVESTOCK_SUMMARY_PATH = PROJECT_ROOT / "outputs" / "CSVs" / "02_espac_livestock_lci_table_filtered__summary_national.csv"
ESPAC_SQLITE_PATH = PROJECT_ROOT / "outputs" / "01_espac_2024.sqlite"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "reports"
OUTPUT_COMBINED_PNG = OUTPUT_DIR / "espac_product_datapoints_wordcloud.png"
OUTPUT_CROP_PNG = OUTPUT_DIR / "espac_crop_product_datapoints_wordcloud.png"
OUTPUT_LIVESTOCK_PNG = OUTPUT_DIR / "espac_livestock_product_datapoints_wordcloud.png"
OUTPUT_COMBINED_COUNTS_CSV = OUTPUT_DIR / "espac_product_datapoints_counts.csv"
OUTPUT_CROP_COUNTS_CSV = OUTPUT_DIR / "espac_crop_product_datapoints_counts.csv"
OUTPUT_LIVESTOCK_COUNTS_CSV = OUTPUT_DIR / "espac_livestock_product_datapoints_counts.csv"


LIVESTOCK_PRODUCT_ES = {
    "cattle_live": "bovinos",
    "donkey_live": "burros",
    "eggs": "huevos",
    "goat_live": "caprinos",
    "horse_live": "caballos",
    "meat_poultry": "carne de pollo",
    "milk": "leche",
    "mule_live": "mulas",
    "ovine_live": "ovinos",
    "swine_live": "cerdos",
}


def _simplify_crop_name(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    text = re.sub(r"\s*\([^)]*\)", "", text)
    text = re.sub(r"\bSECO\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    return {
        "OTROS PERMANENTES": "PERMANENTES SIN DETALLE",
        "OTROS TRANSITORIOS": "TRANSITORIOS SIN DETALLE",
    }.get(text, text)


def _load_other_crop_breakdown(sqlite_path: Path) -> pd.DataFrame:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"Missing ESPAC SQLite database: {sqlite_path}")

    queries = [
        """
        SELECT rc_clacul AS product, COUNT(*) AS count
        FROM inec_cpnac
        WHERE cp_nclavr = 'OTROS PERMANENTES'
        GROUP BY rc_clacul
        """,
        """
        SELECT COALESCE(NULLIF(TRIM(ct_codcultiv1_int), ''), rc_clacul) AS product,
               COUNT(*) AS count
        FROM inec_ctnac
        WHERE ct_nclavr = 'OTROS TRANSITORIOS'
        GROUP BY COALESCE(NULLIF(TRIM(ct_codcultiv1_int), ''), rc_clacul)
        """,
    ]

    with sqlite3.connect(sqlite_path) as conn:
        parts = [pd.read_sql_query(query, conn) for query in queries]

    out = pd.concat(parts, ignore_index=True)
    out["product"] = out["product"].map(_simplify_crop_name)
    out["count"] = pd.to_numeric(out["count"], errors="coerce").fillna(0)
    return out[out["product"].ne("")]


def _load_crop_counts(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"Crop", "count"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in crop summary: {sorted(missing)}")

    out = (
        df[["Crop", "count"]]
        .rename(columns={"Crop": "product"})
        .assign(source="crop")
    )
    out = out[~out["product"].isin(["OTROS PERMANENTES", "OTROS TRANSITORIOS"])]
    out["product"] = out["product"].map(_simplify_crop_name)
    out["count"] = pd.to_numeric(out["count"], errors="coerce").fillna(0)
    other_breakdown = _load_other_crop_breakdown(ESPAC_SQLITE_PATH).assign(source="crop")
    out = pd.concat([out, other_breakdown], ignore_index=True)
    return out


def _load_livestock_counts(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"Product", "count"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in livestock summary: {sorted(missing)}")

    out = (
        df[["Product", "count"]]
        .rename(columns={"Product": "product"})
        .assign(source="livestock")
    )
    out["product"] = out["product"].map(lambda v: LIVESTOCK_PRODUCT_ES.get(str(v).strip(), str(v).strip()))
    out["count"] = pd.to_numeric(out["count"], errors="coerce").fillna(0)
    return out


def _build_frequency_table(counts: pd.DataFrame) -> pd.DataFrame:
    counts = counts.copy()
    counts["product"] = counts["product"].astype(str).str.strip()
    counts = counts[counts["product"].ne("")]

    return (
        counts.groupby("product", as_index=False)["count"]
        .sum()
        .sort_values("count", ascending=False)
    )


def _save_wordcloud(freq_table: pd.DataFrame, output_png: Path) -> int:
    frequencies = {
        row.product: float(row.count)
        for row in freq_table.itertuples(index=False)
        if float(row.count) > 0
    }

    if not frequencies:
        raise ValueError("No positive datapoint counts found to generate the word cloud.")

    wc = WordCloud(
        width=2200,
        height=1400,
        mode="RGBA",
        background_color=None,
        colormap="viridis",
        max_words=400,
        prefer_horizontal=0.9,
        random_state=42,
        collocations=False,
    ).generate_from_frequencies(frequencies)

    wc.to_file(str(output_png))
    return len(frequencies)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    crop_counts = _load_crop_counts(CROP_SUMMARY_PATH)
    livestock_counts = _load_livestock_counts(LIVESTOCK_SUMMARY_PATH)

    crop_freq = _build_frequency_table(crop_counts)
    livestock_freq = _build_frequency_table(livestock_counts)
    combined_freq = _build_frequency_table(
        pd.concat(
            [
                crop_freq.assign(product=lambda d: "cultivo: " + d["product"].astype(str)),
                livestock_freq.assign(product=lambda d: "ganadería: " + d["product"].astype(str)),
            ],
            ignore_index=True,
        )
    )

    combined_n = _save_wordcloud(combined_freq, OUTPUT_COMBINED_PNG)
    crop_n = _save_wordcloud(crop_freq, OUTPUT_CROP_PNG)
    livestock_n = _save_wordcloud(livestock_freq, OUTPUT_LIVESTOCK_PNG)

    combined_freq.rename(columns={"product": "label"}).to_csv(OUTPUT_COMBINED_COUNTS_CSV, index=False)
    crop_freq.to_csv(OUTPUT_CROP_COUNTS_CSV, index=False)
    livestock_freq.to_csv(OUTPUT_LIVESTOCK_COUNTS_CSV, index=False)

    print(f"Combined word cloud saved to: {OUTPUT_COMBINED_PNG}")
    print(f"Combined counts table saved to: {OUTPUT_COMBINED_COUNTS_CSV}")
    print(f"Combined products included: {combined_n}")
    print(f"Crop word cloud saved to: {OUTPUT_CROP_PNG}")
    print(f"Crop counts table saved to: {OUTPUT_CROP_COUNTS_CSV}")
    print(f"Crop products included: {crop_n}")
    print(f"Livestock word cloud saved to: {OUTPUT_LIVESTOCK_PNG}")
    print(f"Livestock counts table saved to: {OUTPUT_LIVESTOCK_COUNTS_CSV}")
    print(f"Livestock products included: {livestock_n}")


if __name__ == "__main__":
    main()
