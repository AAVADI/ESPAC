# ESPAC Crop and Livestock LCI Project Documentation

## 1. Purpose and scope

This repository builds crop and livestock life cycle inventory (LCI) datasets from the 2024 Ecuadorian agricultural survey `ESPAC` and exports them as ecospold/XML process files for downstream LCA use.

The current project covers:

- ETL from the official ESPAC raw delivery into SQLite.
- Crop LCI extraction and aggregation.
- Livestock LCI extraction and aggregation.
- Direct field emissions (DFE) augmentation for crop and livestock inventories.
- Exchange-mapping review for crop XML generation.
- XML export for crop and livestock inventories.

The repository is intended both as:

- an operational pipeline for generating and revising Ecuadorian foreground LCIs; and
- a transparent methodological record for reports and papers using these outputs.

## 2. Current pipeline layout

The workflow is notebook-driven and currently split into crop and livestock branches after a shared ETL step.

### Shared ETL

1. `notebooks/1_espac_2024_etl_to_sqlite.ipynb`

### Crop branch

2. `notebooks/2_crops_espac_2024_sqlite_explorer.ipynb`
3. `notebooks/3_crops_espac_direct_field_emissions.ipynb`
4. `notebooks/4_exchange_grid_roundtrip.ipynb`
5. `notebooks/5_crops_espac_lci_xml_generator.ipynb`

### Livestock branch

2. `notebooks/2_livestock_espac_2024_sqlite_explorer.ipynb`
3. `notebooks/3_livestock_espac_direct_field_emissions.ipynb`
5. `notebooks/5_livestock_espac_lci_xml_generator.ipynb`

Notes:

- Notebook 1 is only needed when rebuilding the SQLite database from raw ESPAC inputs.
- Notebook 4 is only needed for the crop XML exchange-matching workflow.
- The livestock branch does not currently use notebook 4.

## 3. Repository structure

- `inputs/`: raw data, templates, YAML coefficients, and background references.
- `notebooks/`: the numbered pipeline notebooks.
- `scripts/`: helper scripts used mainly by the exchange roundtrip workflow and environment setup.
- `outputs/`: generated SQLite, CSV, spreadsheet, and XML outputs.
- `reports/`: diagnostics, audit tables, and method notes.

## 4. Setup and execution

The repository now includes lightweight setup scripts for reproducible local execution:

- `requirements.txt`
- `scripts/bootstrap_venv.ps1`
- `run-jupyter.ps1`

Recommended setup on Windows PowerShell:

1. Open a terminal in the project root.
2. Run `.\run-jupyter.ps1`.

That script calls `scripts/bootstrap_venv.ps1`, which:

- creates or refreshes `.venv`;
- installs Python dependencies from `requirements.txt`;
- registers the local Jupyter kernel `ESPAC (.venv)`.

If you need Mermaid CLI support for diagram work, install the Node dependency separately with `npm install`. That is not part of the core crop/livestock pipeline.

Typical execution order:

### Crop outputs

1. `1_espac_2024_etl_to_sqlite.ipynb` if SQLite must be rebuilt
2. `2_crops_espac_2024_sqlite_explorer.ipynb`
3. `3_crops_espac_direct_field_emissions.ipynb`
4. `4_exchange_grid_roundtrip.ipynb` if exchange review/editing is needed
5. `5_crops_espac_lci_xml_generator.ipynb`

### Livestock outputs

1. `1_espac_2024_etl_to_sqlite.ipynb` if SQLite must be rebuilt
2. `2_livestock_espac_2024_sqlite_explorer.ipynb`
3. `3_livestock_espac_direct_field_emissions.ipynb`
4. `5_livestock_espac_lci_xml_generator.ipynb`

## 5. Main inputs

### Foreground data

- `inputs/01_2_DD_DATOS_ABIERTOS_ESPAC_2024.zip`

This is the main 2024 ESPAC raw delivery used by notebook 1 to build the analytical SQLite database.

### LCI structure and templates

- `inputs/02_LCI_template.xlsx`
- `inputs/04-05_Model_annual_crops.XML`
- `inputs/04_Model_annual_crops_edited.XML`
- `inputs/livestock00001.XML`
- `inputs/livestock00002.XML`
- `inputs/livestock00003.XML`

Crop XML export uses the crop XML model and the exchange roundtrip artifacts. Livestock XML export uses the livestock template files currently stored as `livestock0000*.XML`.

### Parameters and factors

- `inputs/02-05_espac_lci_coefficients.yml`
- `inputs/03-05_dfe_factors.yml`
- `inputs/03_dfe_nutrient_contents.yml`
- `inputs/03_Factors.xlsx`
- `inputs/01_PRO_data_v1.xlsx`

These files store most of the configurable project logic, including:

- crop and livestock coefficients;
- irrigation and yield proxies;
- fertilizer nutrient assumptions;
- livestock diet, water, electricity, and output-normalization proxies;
- DFE factors and SOC-related settings;
- XML defaults and mapping behavior.

### Background matching references

- `inputs/00_Database_Overview_ecoinvent_v3_12.xlsx`
- `inputs/00_AGRIBALYSE3_2_partie_agriculture_conv_PublieNOV25.xlsx`
- `inputs/00_AGRIBALYSE3_2_Tableur_agriculture_bio_PublieNov24.xlsx`
- `inputs/00_agribalyse_organic_fertilizers.csv`
- `inputs/04_lci_process_catalog.csv`

## 6. Core outputs currently present in the repository

### Shared and intermediate outputs

- `outputs/01_espac_2024.sqlite`
- `outputs/02_latest_filtered_export_summary.json`
- `outputs/02_latest_livestock_filtered_export_summary.json`

These JSON files record the currently selected filtered export metadata for the crop and livestock branches.

### Crop CSV outputs

Tracked crop filtered outputs currently include:

- `summary_region`
- `summary_crop_national`
- `summary_cropping_system`
- `summary_crop_group_national`

Tracked crop DFE outputs currently include:

- `outputs/CSVs/03-05_espac_crop_lci_table_filtered_dfe__summary_region.csv`
- `outputs/CSVs/03-05_espac_crop_lci_table_filtered_dfe__summary_crop_national.csv`
- `outputs/CSVs/03-05_espac_crop_lci_table_filtered_dfe__summary_cropping_system.csv`
- `outputs/CSVs/03-05_espac_crop_lci_table_filtered_dfe__summary_crop_group_national.csv`

Corresponding uncertainty tables are stored beside them with the `_uncertainty.csv` suffix.

### Livestock CSV outputs

Tracked livestock outputs currently include summary tables for:

- `province`
- `region`
- `national`
- `product`

Tracked livestock DFE outputs currently include:

- `outputs/CSVs/03-05_espac_livestock_lci_table_filtered_dfe__summary_region.csv`
- `outputs/CSVs/03-05_espac_livestock_lci_table_filtered_dfe__summary_national.csv`
- `outputs/CSVs/03-05_espac_livestock_lci_table_filtered_dfe__summary_product.csv`

Corresponding uncertainty tables are stored beside them with the `_uncertainty.csv` suffix.

Additional synthetic or locked diagnostic exports may exist locally, but they are not part of the committed core workflow unless explicitly versioned.

### XML outputs

Tracked crop XML outputs currently exist in:

- `outputs/05_xml_exports_crop_lci/summary_crop_group_national/`
- `outputs/05_xml_exports_crop_lci/summary_crop_national/`
- `outputs/05_xml_exports_crop_lci/summary_region/`

Tracked livestock XML outputs currently exist in:

- `outputs/05_xml_exports_livestock_lci/summary_product/`

## 7. Workflow summary

### 7.1 Notebook 1: ETL to SQLite

`notebooks/1_espac_2024_etl_to_sqlite.ipynb`:

- reads the nested ESPAC ZIP delivery;
- imports survey tables into SQLite;
- imports dictionary content into metadata tables;
- prepares the working database used downstream.

Main output:

- `outputs/01_espac_2024.sqlite`

### 7.2 Notebook 2 crops: crop LCI extraction and aggregation

`notebooks/2_crops_espac_2024_sqlite_explorer.ipynb`:

- extracts crop and cultivated-pasture management records from the SQLite database;
- transforms ESPAC records into an LCI-like crop table;
- computes derived variables and grouped summaries;
- exports filtered summary tables plus uncertainty tables.

Current crop summary levels reflected in the repo include:

- `province`
- `region`
- `crop_national`
- `cropping_system`
- `crop_group_national`

Cultivated pasture is treated as part of the crop-side foreground system and exported with its own grouping behavior.

### 7.3 Notebook 2 livestock: livestock LCI extraction and aggregation

`notebooks/2_livestock_espac_2024_sqlite_explorer.ipynb`:

- extracts livestock, milk, and egg records from livestock-related ESPAC modules;
- converts them into livestock LCI tables;
- applies aggregation and uncertainty export logic;
- exports filtered livestock summary tables.

Products currently represented in the repo include:

- cattle live
- milk
- swine live
- ovine live
- goat live
- eggs
- poultry meat grouped as `meat_poultry_product` at XML level

The livestock pipeline also writes a cattle pasture linkage diagnostic:

- `outputs/CSVs/02_espac_cattle_pasture_linkage_diagnostic.csv`

That file is useful diagnostically but should be treated as a supporting analysis table rather than a final LCI product.

### 7.4 Notebook 3 crops: crop DFE augmentation

`notebooks/3_crops_espac_direct_field_emissions.ipynb`:

- reads the filtered crop summary selected in `outputs/02_latest_filtered_export_summary.json`;
- adds crop direct field emission estimates;
- exports DFE-augmented crop tables and uncertainty tables.

The crop DFE stage currently supports the committed summary outputs present in the repo, especially:

- `summary_region`
- `summary_crop_national`
- `summary_crop_group_national`
- `summary_cropping_system`

### 7.5 Notebook 3 livestock: livestock DFE augmentation

`notebooks/3_livestock_espac_direct_field_emissions.ipynb`:

- reads the filtered livestock summary selected in `outputs/02_latest_livestock_filtered_export_summary.json`;
- applies the current exploratory livestock DFE logic;
- exports DFE-augmented livestock tables and uncertainty tables.

The livestock DFE branch is explicitly exploratory and proxy-heavy. It is operational, but its outputs should still be documented carefully as a developing component.

### 7.6 Notebook 4: crop exchange roundtrip

`notebooks/4_exchange_grid_roundtrip.ipynb`:

- prepares crop exchange review tables;
- supports matching foreground exchanges to background datasets;
- interacts with the helper scripts in `scripts/`.

Important helper scripts include:

- `scripts/nb04_process_name_matcher.py`
- `scripts/nb04_xml_exchange_table_tool.py`
- `scripts/check_simapro_import_bundle.py`
- `scripts/fix_simapro_reference_categories.py`
- `scripts/fix_simapro_reference_exchange_comment.py`

This stage is still partly manual and is the least automated part of the crop workflow.

### 7.7 Notebook 5 crops: crop XML generation

`notebooks/5_crops_espac_lci_xml_generator.ipynb`:

- reads crop DFE outputs;
- applies the crop XML template and exchange mapping logic;
- writes XML files for the supported crop summary levels.

The current committed crop XML naming scheme is simplified compared with older legacy names. For example, files are now written as:

- `00001_cereals_summary_crop_group_national.xml`
- `00001_AGUACATE_FRUTA_FRESCA__summary_crop_national.xml`
- `00001_AGUACATE_FRUTA_FRESCA__costa_summary_region.xml`

### 7.8 Notebook 5 livestock: livestock XML generation

`notebooks/5_livestock_espac_lci_xml_generator.ipynb`:

- reads livestock DFE or filtered livestock LCI outputs;
- applies the livestock XML templates;
- writes livestock XML files to `outputs/05_xml_exports_livestock_lci/summary_product/`.

Current committed livestock XML outputs include:

- `cattle_live_product.xml`
- `eggs_product.xml`
- `goat_live_product.xml`
- `meat_poultry_product.xml`
- `milk_product.xml`
- `ovine_live_product.xml`
- `swine_live_product.xml`

## 8. Current methodological features reflected in the repo

### Crop side

The crop workflow currently includes:

- crop and cultivated-pasture extraction;
- grouping at several geographic and product levels;
- YAML-driven yield and coefficient logic;
- crop DFE augmentation;
- crop XML export for region, crop-national, and crop-group-national summaries.

Permanent-system SOC handling is now integrated into the crop DFE and crop XML chain through the current DFE configuration file. Some coefficients are still proxies and should be treated as provisional rather than Ecuador-specific final parameters.

### Livestock side

The livestock workflow currently includes:

- species/product-specific extraction from ESPAC livestock modules;
- proxy completion for diet, water, electricity, and output normalization;
- cattle pasture linkage logic;
- exploratory livestock DFE augmentation;
- livestock XML export at `summary_product` level.

This livestock branch is materially more advanced than the earlier exploratory repo state and should now be considered an implemented workflow, while still carrying stronger proxy limitations than the crop branch.

## 9. Important assumptions and limitations

Users should document the following clearly when using repository outputs:

1. The foreground source is the 2024 Ecuador ESPAC survey.
2. Crop and livestock pipelines are now separate after the ETL stage.
3. Numeric aggregation uses grouped medians and uncertainty is represented with empirical within-group minimum and maximum values.
4. Many parameters remain proxy-based because ESPAC does not directly report all LCI-relevant variables.
5. The crop exchange roundtrip remains partly manual.
6. The livestock DFE workflow is operational but still exploratory and literature-driven.
7. Several crop SOC coefficients and many livestock proxy factors are still best-available placeholders rather than Ecuador-calibrated final values.

Examples of major proxy-dependent areas include:

- irrigation requirements and efficiencies;
- fertilizer composition assumptions;
- pesticide active-ingredient allocation;
- crop residue and SOC parameters;
- livestock diet completion;
- livestock water and electricity use;
- livestock live-weight and FPCM normalization;
- direct field emission factors imported from non-Ecuador literature.

## 10. Diagnostics and supporting reports

Important tracked report outputs include:

- `reports/05_ecuador_pesticide_method_note.md`
- `reports/05_legacy_input_requirements_report.csv`
- `reports/05_xml_uncertainty_audit_report.csv`

The crop XML readiness report remains relevant because some legacy template expectations are still only partially populated even though the current operational export path works for the committed XML outputs.

## 11. Reproducibility notes

The project is still notebook-driven rather than orchestrated by a single CLI pipeline. Reproducibility currently depends on:

- stable folder structure;
- consistent notebook execution order;
- stable input filenames in `inputs/`;
- correct use of the local `.venv` environment;
- manual care during crop exchange review when notebook 4 is used.

The current setup scripts improve reproducibility compared with earlier repo versions by standardizing environment creation and Jupyter kernel registration.

## 12. Recommended citation metadata

When citing outputs from this repository, record at minimum:

- ESPAC survey year: `2024`
- branch used: `crop` or `livestock`
- summary level used: for example `region`, `crop_national`, `crop_group_national`, `cropping_system`, `province`, `national`, or `product`
- repository commit hash
- date of generated outputs
- XML template version used
- background database references used in exchange matching

## 13. Files most relevant to users

- `notebooks/1_espac_2024_etl_to_sqlite.ipynb`
- `notebooks/2_crops_espac_2024_sqlite_explorer.ipynb`
- `notebooks/2_livestock_espac_2024_sqlite_explorer.ipynb`
- `notebooks/3_crops_espac_direct_field_emissions.ipynb`
- `notebooks/3_livestock_espac_direct_field_emissions.ipynb`
- `notebooks/4_exchange_grid_roundtrip.ipynb`
- `notebooks/5_crops_espac_lci_xml_generator.ipynb`
- `notebooks/5_livestock_espac_lci_xml_generator.ipynb`
- `inputs/02-05_espac_lci_coefficients.yml`
- `inputs/03-05_dfe_factors.yml`
- `reports/05_ecuador_pesticide_method_note.md`
- `reports/05_legacy_input_requirements_report.csv`
- `reports/05_xml_uncertainty_audit_report.csv`

## 14. Documentation maintenance note

`ESPAC_project_documentation.md` should be updated whenever approved implementation changes affect:

- notebook structure;
- input files used by the pipeline;
- exported output sets;
- naming conventions;
- major assumptions or proxy methods;
- setup or reproducibility workflow.

At the current project state, the most important recent developments reflected in this document are:

- the split crop/livestock notebook architecture;
- committed livestock CSV and XML outputs;
- the new PowerShell environment/bootstrap workflow;
- the current crop XML naming scheme and committed crop output coverage.
