from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = PROJECT_DIR / "outputs" / "CSVs"
DEFAULT_DOCS_DIR = PROJECT_DIR / "docs"


DATASETS: list[dict[str, Any]] = [
    {
        "id": "crops-stage02-province",
        "label": "Crops - Stage 02 - Province",
        "description": "Province-level crop LCI tables generated from the crop pipeline.",
        "main_csv": "02_espac_crop_lci_table__summary_province.csv",
        "uncertainty_csv": "02_espac_crop_lci_table__summary_province_uncertainty.csv",
    },
    {
        "id": "crops-stage02-crop-group-national",
        "label": "Crops - Stage 02 - Crop group national",
        "description": "National crop-group LCI tables from the stage 02 crop output.",
        "main_csv": "02_espac_crop_lci_table_filtered__summary_crop_group_national.csv",
        "uncertainty_csv": "02_espac_crop_lci_table_filtered__summary_crop_group_national_uncertainty.csv",
    },
    {
        "id": "livestock-stage02-national",
        "label": "Livestock - Stage 02 - National",
        "description": "National livestock LCI tables from the stage 02 livestock output.",
        "main_csv": "02_espac_livestock_lci_table_filtered__summary_national.csv",
        "uncertainty_csv": "02_espac_livestock_lci_table_filtered__summary_national_uncertainty.csv",
    },
    {
        "id": "crops-stage0305-crop-group-national",
        "label": "Crops - Stage 03-05 - Crop group national",
        "description": "Crop-group national LCI tables after direct field emissions and XML generation.",
        "main_csv": "03-05_espac_crop_lci_table_filtered_dfe__summary_crop_group_national.csv",
        "uncertainty_csv": "03-05_espac_crop_lci_table_filtered_dfe__summary_crop_group_national_uncertainty.csv",
    },
    {
        "id": "livestock-stage0305-national",
        "label": "Livestock - Stage 03-05 - National",
        "description": "National livestock LCI tables after direct field emissions and XML generation.",
        "main_csv": "03-05_espac_livestock_lci_table_filtered_dfe__summary_national.csv",
        "uncertainty_csv": "03-05_espac_livestock_lci_table_filtered_dfe__summary_national_uncertainty.csv",
    },
]


def stringify_cell(value: Any) -> str | None:
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, (int, np.integer)):
        return str(value)
    if isinstance(value, (float, np.floating)):
        if pd.isna(value):
            return None
        return format(value, ".12g")
    return str(value)


def csv_to_json(csv_path: Path, json_path: Path) -> dict[str, Any]:
    df = pd.read_csv(csv_path, low_memory=False)
    columns = [str(col) for col in df.columns]
    rows = [
        [stringify_cell(value) for value in row]
        for row in df.itertuples(index=False, name=None)
    ]
    payload = {
        "source": csv_path.name,
        "rowCount": int(len(df)),
        "columnCount": int(len(columns)),
        "columns": columns,
        "rows": rows,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def build_site(source_dir: Path, docs_dir: Path) -> None:
    docs_dir.mkdir(parents=True, exist_ok=True)
    data_dir = docs_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    manifest_datasets: list[dict[str, Any]] = []
    for spec in DATASETS:
        main_csv = source_dir / spec["main_csv"]
        unc_csv = source_dir / spec["uncertainty_csv"]
        if not main_csv.exists():
            raise FileNotFoundError(f"Missing required CSV: {main_csv}")
        if not unc_csv.exists():
            raise FileNotFoundError(f"Missing required CSV: {unc_csv}")

        main_json = data_dir / f"{spec['id']}-main.json"
        unc_json = data_dir / f"{spec['id']}-uncertainty.json"
        main_payload = csv_to_json(main_csv, main_json)
        unc_payload = csv_to_json(unc_csv, unc_json)

        manifest_datasets.append(
            {
                "id": spec["id"],
                "label": spec["label"],
                "description": spec["description"],
                "main": {
                    "path": f"data/{main_json.name}",
                    "source": spec["main_csv"],
                    "rowCount": main_payload["rowCount"],
                    "columnCount": main_payload["columnCount"],
                },
                "uncertainty": {
                    "path": f"data/{unc_json.name}",
                    "source": spec["uncertainty_csv"],
                    "rowCount": unc_payload["rowCount"],
                    "columnCount": unc_payload["columnCount"],
                },
            }
        )

    manifest = {
        "appName": "ESPAC LCI Explorer",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "datasetCount": len(manifest_datasets),
        "datasets": manifest_datasets,
    }
    (docs_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (docs_dir / ".nojekyll").write_text("", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the static GitHub Pages site for ESPAC LCI tables.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_site(args.source_dir, args.docs_dir)
    print(f"Built GitHub Pages site in: {args.docs_dir}")


if __name__ == "__main__":
    main()
