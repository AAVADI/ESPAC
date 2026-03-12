# Project Reorganization Map

## Folder layout
- `notebooks/`: numbered analysis/generation notebooks.
- `scripts/`: Python helper modules used by notebooks.
- `inputs/`: static/raw/reference inputs.
- `outputs/`: generated data products and XML exports.
- `reports/`: notes, diagnostics, audit outputs.

## Numbering convention
- `01_...` used by notebook 1
- `02_...` used by notebook 2
- `03_...` used by notebook 3
- `04_...` used by notebook 4
- `05_...` used by notebook 5
- `02-05_...` used by multiple notebooks (here: 2 and 5), etc.
- `00_...` unlinked/common reference material.

## Main renamed paths
- `scripts/nb04_xml_exchange_table_tool.py`
- `scripts/nb04_process_name_matcher.py`
- `inputs/01_2_DD_DATOS_ABIERTOS_ESPAC_2024.zip`
- `inputs/02_LCI_template.xlsx`
- `inputs/02-05_espac_lci_coefficients.yml`
- `inputs/03-05_dfe_factors.yml`
- `inputs/03_dfe_nutrient_contents.yml`
- `inputs/03_Factors.xlsx`
- `inputs/04-05_Model_annual_crops.XML`
- `inputs/04_Model_annual_crops_edited.XML`
- `inputs/04_lci_process_catalog.csv`
- `outputs/01_espac_2024.sqlite`
- `outputs/02_espac_crop_lci_table.csv`
- `outputs/02_espac_crop_lci_table_uncertainty.csv`
- `outputs/02_espac_crop_lci_table_filtered.csv`
- `outputs/02-03-05_espac_crop_lci_table_filtered_uncertainty.csv`
- `outputs/03-05_espac_crop_lci_table_filtered_dfe.csv`
- `outputs/03_espac_crop_lci_table_filtered_dfe_uncertainty.csv`
- `outputs/04_exchanges_table.xlsx`
- `outputs/04_exchanges_table_with_process_matches.xlsx`
- `outputs/05_xml_exports_crop_lci/`
- `reports/05_legacy_input_requirements_report.csv`
- `reports/05_xml_uncertainty_audit_report.csv`

## Important note
- The environment denied file deletion/rename on existing originals (OneDrive/permission lock behavior). The reorganized copies are in place and notebooks were updated to point to the new folders.
