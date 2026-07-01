from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

try:
    from scripts.crop_groups import canonical_crop_group_token
except ModuleNotFoundError:
    from crop_groups import canonical_crop_group_token


PROJECT_DIR = Path(__file__).resolve().parents[1]
COEFFICIENTS_PATH = PROJECT_DIR / "inputs" / "02-05_espac_lci_coefficients.yml"
DFE_FACTORS_PATH = PROJECT_DIR / "inputs" / "03-05_dfe_factors.yml"

COMPARTMENTS = {
    "air": "PrimAir",
    "soil": "PrimSoil",
    "water": "PrimWater",
}
CROP_TYPE_PREFIX = {
    "cereal": "c",
    "fruit": "f",
    "vegetable": "v",
}
DEFAULT_PREFIX = "c"


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _column_token(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value).lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _numeric(series: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default).astype(float)


def _numeric_with_fallback(series: pd.Series, fallback: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return values.fillna(fallback).astype(float)


def _row_text(row: pd.Series, column: str) -> str:
    value = row.get(column, "")
    return "" if pd.isna(value) else str(value).strip()


def _molecule_catalog(coefficients: dict[str, Any]) -> list[str]:
    names: dict[str, str] = {}
    for section_name in (
        "pesticide_molecule_shares_by_crop",
        "pesticide_molecule_shares_by_crop_group",
    ):
        for payload in (coefficients.get(section_name, {}) or {}).values():
            for item in (payload or {}).get("molecules", []) or []:
                molecule = str(item.get("molecule", "")).strip()
                if molecule:
                    names.setdefault(_column_token(molecule), molecule)
    return [names[token] for token in sorted(names)]


def _shares_for_row(row: pd.Series, coefficients: dict[str, Any]) -> dict[str, float]:
    crop_name = _row_text(row, "Crop").upper()
    by_crop = coefficients.get("pesticide_molecule_shares_by_crop", {}) or {}
    payload = by_crop.get(crop_name, {}) or {}

    if not (payload.get("molecules", []) or []):
        group = canonical_crop_group_token(_row_text(row, "Crop_group"))
        by_group = coefficients.get("pesticide_molecule_shares_by_crop_group", {}) or {}
        payload = by_group.get(group, {}) or {}

    shares: dict[str, float] = {}
    for item in payload.get("molecules", []) or []:
        molecule = str(item.get("molecule", "")).strip()
        share = float(item.get("contribution_percent", 0.0) or 0.0)
        if molecule and share > 0:
            token = _column_token(molecule)
            shares[token] = shares.get(token, 0.0) + share
    return shares


def _partition_prefix(row: pd.Series) -> str:
    crop_type = _row_text(row, "Custom_classification_3").lower()
    if crop_type not in CROP_TYPE_PREFIX:
        crop_type = _row_text(row, "crop_type_dfe").lower()
    return CROP_TYPE_PREFIX.get(crop_type, DEFAULT_PREFIX)


def _emission_column(molecule: str, compartment: str) -> str:
    return f"PesticideEmission_{_column_token(molecule)}_{compartment}_kg_ha"


def add_partitioned_pesticide_emissions(
    main_df: pd.DataFrame,
    uncertainty_df: pd.DataFrame,
    coefficients_path: Path = COEFFICIENTS_PATH,
    factors_path: Path = DFE_FACTORS_PATH,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Append XML-equivalent pesticide emissions and uncertainty to DFE tables."""
    main = main_df.copy()
    uncertainty = uncertainty_df.copy()
    if len(main) != len(uncertainty):
        raise ValueError(
            "Main and uncertainty DFE tables must have the same row count "
            f"({len(main)} != {len(uncertainty)})."
        )

    main = main.drop(
        columns=[column for column in main if column.startswith("PesticideEmission_")],
        errors="ignore",
    )
    uncertainty = uncertainty.drop(
        columns=[column for column in uncertainty if column.startswith("PesticideEmission_")],
        errors="ignore",
    )

    coefficients = _load_yaml(coefficients_path)
    factors = (_load_yaml(factors_path).get("knime_factors", {}) or {})
    molecules = _molecule_catalog(coefficients)
    shares_by_row = [_shares_for_row(row, coefficients) for _, row in main.iterrows()]
    prefixes = [_partition_prefix(row) for _, row in main.iterrows()]

    total = _numeric(main.get("Total_pesticides_kgha", pd.Series(0.0, index=main.index)))
    raw_min = _numeric_with_fallback(
        uncertainty.get("Total_pesticides_kgha__minValue", total),
        total,
    )
    raw_max = _numeric_with_fallback(
        uncertainty.get("Total_pesticides_kgha__maxValue", total),
        total,
    )
    total_min = pd.concat([raw_min, raw_max], axis=1).min(axis=1)
    total_max = pd.concat([raw_min, raw_max], axis=1).max(axis=1)

    main_emissions: dict[str, pd.Series] = {}
    uncertainty_emissions: dict[str, pd.Series] = {}
    for compartment, factor_suffix in COMPARTMENTS.items():
        factor = pd.Series(
            [float(factors.get(f"{prefix}_{factor_suffix}", 0.0) or 0.0) / 100.0 for prefix in prefixes],
            index=main.index,
            dtype=float,
        )
        compartment_values: list[pd.Series] = []
        compartment_min_values: list[pd.Series] = []
        compartment_max_values: list[pd.Series] = []
        for molecule in molecules:
            token = _column_token(molecule)
            share = pd.Series(
                [row_shares.get(token, 0.0) / 100.0 for row_shares in shares_by_row],
                index=main.index,
                dtype=float,
            )
            column = _emission_column(molecule, compartment)
            value = total * share * factor
            min_value = total_min * share * factor
            max_value = total_max * share * factor
            main_emissions[column] = value
            uncertainty_emissions[f"{column}__minValue"] = min_value
            uncertainty_emissions[f"{column}__maxValue"] = max_value
            compartment_values.append(value)
            compartment_min_values.append(min_value)
            compartment_max_values.append(max_value)

        total_column = f"PesticideEmission_total_{compartment}_kg_ha"
        main_emissions[total_column] = sum(compartment_values, pd.Series(0.0, index=main.index))
        uncertainty_emissions[f"{total_column}__minValue"] = sum(
            compartment_min_values,
            pd.Series(0.0, index=main.index),
        )
        uncertainty_emissions[f"{total_column}__maxValue"] = sum(
            compartment_max_values,
            pd.Series(0.0, index=main.index),
        )

    main = pd.concat([main, pd.DataFrame(main_emissions, index=main.index)], axis=1)
    uncertainty = pd.concat(
        [uncertainty, pd.DataFrame(uncertainty_emissions, index=uncertainty.index)],
        axis=1,
    )

    return main, uncertainty


def enrich_csv_pair(main_path: Path, uncertainty_path: Path) -> tuple[int, int]:
    main = pd.read_csv(main_path)
    uncertainty = pd.read_csv(uncertainty_path)
    enriched_main, enriched_uncertainty = add_partitioned_pesticide_emissions(main, uncertainty)
    enriched_main.to_csv(main_path, index=False, encoding="utf-8-sig")
    enriched_uncertainty.to_csv(uncertainty_path, index=False, encoding="utf-8-sig")
    return enriched_main.shape[1], enriched_uncertainty.shape[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Add partitioned pesticide emissions to crop DFE CSVs.")
    parser.add_argument("main_csv", type=Path)
    parser.add_argument("uncertainty_csv", type=Path)
    args = parser.parse_args()
    main_columns, uncertainty_columns = enrich_csv_pair(args.main_csv, args.uncertainty_csv)
    print(
        f"Enriched {args.main_csv.name} ({main_columns} columns) and "
        f"{args.uncertainty_csv.name} ({uncertainty_columns} columns)."
    )


if __name__ == "__main__":
    main()
