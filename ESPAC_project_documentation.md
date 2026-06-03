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

The project now supports two complementary execution modes:

- a notebook workflow, which remains the methodological and implementation backbone; and
- an interactive marimo app in `apps/espac_lci_pipeline_marimo.py`, which acts as the operational frontend for routine execution, previewing, and export.

In both modes, the project is split into crop and livestock branches after a shared ETL step.

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
- The marimo app orchestrates routine stage execution, previewing, cache building, and XML export from these notebook- and script-backed stages.
- The numbered notebooks remain the primary methodological record and the most direct way to inspect intermediate logic cell by cell.

## 3. Repository structure

- `inputs/`: raw data, templates, YAML coefficients, and background references.
- `notebooks/`: the numbered pipeline notebooks.
- `scripts/`: helper scripts used mainly by the exchange roundtrip workflow and environment setup.
- `apps/`: interactive marimo app entrypoints for operational pipeline use.
- `outputs/`: generated SQLite, CSV, spreadsheet, and XML outputs.
- `reports/`: diagnostics, audit tables, and method notes.

## 4. Setup and execution

The repository now includes lightweight setup scripts for reproducible local execution:

- `requirements.txt`
- `scripts/bootstrap_venv.ps1`
- `run-jupyter.ps1`
- `scripts/run_marimo_clean.ps1`
- `scripts/run_marimo_clean.sh`

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
2. `2_livestock_espac_2024_sqlite_explorer.ipynb` (integrated v2 stage `02`)
3. `3_livestock_espac_direct_field_emissions.ipynb` (integrated v2 stage `03-05`)
4. `5_livestock_espac_lci_xml_generator.ipynb` (integrated v2 stage `05_xml`)

The canonical livestock implementation is now orchestrated by:

- `scripts/livestock_pipeline_v2_integrated.py`

This script is the source of truth for livestock stage integration (`02`, `03-05`, `05_xml`), metadata refresh (`outputs/02_latest_livestock_filtered_export_summary.json`), and manifest lineage updates.

Recommended usage pattern:

- use the notebooks when inspecting methodology, validating transformations, or developing new logic;
- use the marimo app for routine execution, quick previewing, cache building, and export operations.

## 5. Main inputs

### Foreground data

- `inputs/01_2_DD_DATOS_ABIERTOS_ESPAC_2024.zip`

This is the main 2024 ESPAC raw delivery used by notebook 1 to build the analytical SQLite database.

### LCI structure and templates

- `inputs/02_LCI_template.xlsx`
- `inputs/04-05_Model_annual_crops.XML`
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
- `outputs/pipeline_run_manifest.json`
- `outputs/02_latest_filtered_export_summary.json`
- `outputs/02_latest_livestock_filtered_export_summary.json`

`outputs/pipeline_run_manifest.json` is now the authoritative run registry used to track immutable stage snapshots (`02`, `03-05`, and `05_xml`) and to resolve notebook 6 data runs.
The `02_latest_...json` files remain for compatibility and convenience, but they are advisory when manifest records exist.

### Crop CSV outputs

Tracked crop filtered outputs currently include:

- `summary_province`
- `summary_region`
- `summary_crop_national`
- `summary_cropping_system`
- `summary_crop_group_national`

Tracked crop DFE outputs currently include:

- `outputs/CSVs/03-05_espac_crop_lci_table_filtered_dfe__summary_province.csv`
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

`product` is no longer an active livestock strategy. The previous product-level path has been superseded by the integrated V2 national workflow.

Livestock summary tables now include explicit product-routed animal input columns, such as `Animal_input_calf_live_weight_kg_per_1kg_product`, `Animal_input_piglet_live_weight_kg_per_1kg_product`, and `Animal_input_kid_goat_live_weight_kg_per_1kg_product`. These columns are generated during the CSV stage so downstream DFE and XML steps do not have to infer the concerned animal from the shared `Animals_total_live_weight_kg_per_1kg_product` value. Where the routed animal input is an economically allocated technosphere process, notebook 2 applies the process allocation factor directly to the median, minimum, and maximum values before export. For cattle, swine, and ovine meat rows, notebook 2 also applies an `Animal_input_age_related_factor` before aggregation so uncertainty bounds are based on ESPAC stock/outflow variation rather than a flat carcass-yield constant; goat kid-goat and meat-poultry one-day-chicken bounds use aggregate live-weight/reference-output ranges when no usable sales/outflow field is available. CSV-stage non-pasture compound-feed components (`Supplement_feed_kg_per_1kg_product`, `Common_feed_kg_per_1kg_product`, `Waste_feed_kg_per_1kg_product`, `Unallocated_feed_kg_per_1kg_product`, and `Proxy_compound_feed_kg_per_1kg_product`) are scaled by the ratio between the routed animal input and the generic animal live-weight basis before feed totals are recomputed, so compound feed follows the concerned input animal rather than the unallocated herd basis.

Tracked livestock DFE outputs currently include:

- `outputs/CSVs/03-05_espac_livestock_lci_table_filtered_dfe__summary_province.csv`
- `outputs/CSVs/03-05_espac_livestock_lci_table_filtered_dfe__summary_region.csv`
- `outputs/CSVs/03-05_espac_livestock_lci_table_filtered_dfe__summary_national.csv`

Corresponding uncertainty tables are stored beside them with the `_uncertainty.csv` suffix.

### Reference caches

The repository now supports two optional expensive-build reference caches used by the marimo app:

- `outputs/CSVs/reference_cache_crops_all_combinations.csv`
- `outputs/CSVs/reference_cache_livestock_all_combinations.csv`

These caches accelerate previewing across supported configuration combinations. They are derived artifacts, not source-of-truth pipeline outputs.

Additional synthetic or locked diagnostic exports may exist locally, but they are not part of the committed core workflow unless explicitly versioned.

### XML outputs

Tracked crop XML outputs currently exist in:

- `outputs/05_xml_exports_crop_lci/summary_cropping_system/`
- `outputs/05_xml_exports_crop_lci/summary_crop_group_national/`
- `outputs/05_xml_exports_crop_lci/summary_crop_national/`
- `outputs/05_xml_exports_crop_lci/summary_province/`
- `outputs/05_xml_exports_crop_lci/summary_region/`

Tracked livestock XML outputs currently exist in:

- `outputs/05_xml_exports_livestock_lci/summary_province/`
- `outputs/05_xml_exports_livestock_lci/summary_region/`
- `outputs/05_xml_exports_livestock_lci/summary_national/`

### Current XML naming convention

Livestock XML filenames no longer use `strategy_X` tags. The active naming scheme is semantic and encodes the product plus aggregation meaning directly.

Examples:

- `product_cattle_live_aggregation_national.xml`
- `product_milk_aggregation_national.xml`
- `product_swine_live_aggregation_region.xml`

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
- `irrig_m3_class`
- `farm_size_class`
- `crop_group`
- `crop_group_national`

Cultivated pasture is treated as part of the crop-side foreground system and exported with its own grouping behavior.

#### 7.2.1 Curated crop-group membership source

Crop-group membership (for example `cereals`, `fruits`, `vegetables`) is maintained as a curated list in:

- `scripts/crop_groups.py` (`_build_curated_map`)

This file is the authoritative implementation used by the crop pipeline when assigning `Crop_group` values.

Project notes describing the intended constituency list are also recorded in:

- `ToDo.txt` (section beginning with "improve the crop groups management strategy...")

Only four explicit exception labels are allowed to use rule-based routing outside the curated direct map:

- `OTROS PERMANENTES`
- `OTROS TRANSITORIOS`
- `VIVEROS DE PERMANENTES`
- `VIVEROS TRANSITORIOS`

All other crop-group assignments should come from the curated list in `scripts/crop_groups.py`.

### 7.3 Notebook 2 livestock: livestock LCI extraction and aggregation

`notebooks/2_livestock_espac_2024_sqlite_explorer.ipynb`:

- extracts livestock, milk, and egg records from livestock-related ESPAC modules;
- converts them into livestock LCI tables;
- assigns explicit product-routed animal input columns for meat, milk, and egg inventories;
- applies aggregation and uncertainty export logic;
- exports filtered livestock summary tables.

Products currently represented in the repo include:

- milk
- swine live
- ovine live
- eggs
- poultry meat
- cattle meat
- other_livestock_live

The livestock pipeline also writes a cattle pasture linkage diagnostic:

- `outputs/CSVs/02_espac_cattle_pasture_linkage_diagnostic.csv`

That file is useful diagnostically but should be treated as a supporting analysis table rather than a final LCI product.

#### 7.3.1 Milk cow productive-life determination (latest update)

Milk live-weight normalization in notebook 2 now amortizes producing-cow biomass over an explicit Ecuador milk-producing-years parameter.

Current implementation:

- parameter key: `livestock_output_normalization.milk.producing_years_ec`
- parameter file value: `5.5` years in `inputs/02-05_espac_lci_coefficients.yml`
- notebook fallback default aligned to `5.5` in `notebooks/2_livestock_espac_2024_sqlite_explorer.ipynb`

The internal ESPAC hint used for calibration comes from a weighted stock/outflow ratio built from survey variables:

- weighted milking-cow stock proxy: `gl_k812 + gl_vacajeord`
- weighted annual adult-cow outflow proxy: `vgv_nchvacas`
- expansion factor: `fact_exp_fin`

Computed national hint (latest run):

- `sum((gl_k812 + gl_vacajeord) * fact_exp_fin) / sum(vgv_nchvacas * fact_exp_fin) = 6.933344` years

Reproducible estimator snippet (Python + SQLite):

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("outputs/01_espac_2024.sqlite")
gl = pd.read_sql_query(
    "SELECT identificador, fact_exp_fin, gl_k812, gl_vacajeord FROM inec_glnac",
    conn,
)
vgv = pd.read_sql_query(
    "SELECT identificador, vgv_nchvacas FROM inec_vgvnac",
    conn,
)
conn.close()

def num(s):
    return pd.to_numeric(s, errors="coerce").fillna(0.0)

gl = gl.groupby("identificador", as_index=False).first()
vgv = vgv.groupby("identificador", as_index=False).first()

gl["w"] = pd.to_numeric(gl["fact_exp_fin"], errors="coerce").fillna(0.0)
gl["milked_cows"] = num(gl["gl_k812"]) + num(gl["gl_vacajeord"])
vgv["sold_adult_cows"] = num(vgv["vgv_nchvacas"])

m = gl[["identificador", "w", "milked_cows"]].merge(
    vgv[["identificador", "sold_adult_cows"]],
    on="identificador",
    how="left",
).fillna(0.0)

years_hint = (m["milked_cows"] * m["w"]).sum() / (m["sold_adult_cows"] * m["w"]).sum()
print(years_hint)  # 6.933344 (latest run)
```

Because the project decision target for milk-cow productive age was constrained to a 5 to 6 year range, the operational value was set to `5.5` years as a conservative midpoint within that band.

#### 7.3.2 Egg laying-hen productive-life determination

Egg live-weight and hen-feed normalization now follows the same productive-life amortization pattern used for milk-producing cows.

Current implementation:

- parameter key: `livestock_output_normalization.eggs.producing_years_ec`
- parameter file value: `1.5` years in `inputs/02-05_espac_lci_coefficients.yml`
- egg output period key: `livestock_output_normalization.eggs.output_periods_per_year`
- egg output period value: `52`, because ESPAC `ap_k1238`/`ap_k1240` egg counts are treated as weekly egg output/destination counts before conversion to annual kg shell eggs
- notebook fallback default aligned to `1.5` in `notebooks/2_livestock_espac_2024_sqlite_explorer.ipynb`

Notebook 2 annualizes reported egg counts with 52 periods/year before converting to kg shell eggs. It also applies the productive-life parameter before CSV export by dividing laying-hen live weight and per-head feed proxy columns by the configured egg-producing years. The resulting `Animal_input_laying_hen_live_weight_kg_per_1kg_product` and feed-per-kg columns are therefore already productive-life amortized before DFE and XML generation. The CSV-stage compound-feed proportionality rule also applies to egg proxy and total feed, although the current egg ratio is one because the routed laying-hen input and generic laying-hen live-weight basis are aligned after productive-life normalization.

Egg land occupation and transformation are also populated from the configured non-cage layer-house area proxy in `livestock_infra_water_electricity_proxy_table.eggs` (`area_m2_head = 0.286`, using `producing_animals_head`). Notebook 2 converts this to `Infrastructure_area_ha` and fills `Area_ha` where no direct ESPAC poultry area is available, so `Area_ha_per_1kg_product` is available for the strategy 9 XML land-use exchanges.

### 7.4 Notebook 3 crops: crop DFE augmentation

`notebooks/3_crops_espac_direct_field_emissions.ipynb`:

- reads the filtered crop summary selected in `outputs/02_latest_filtered_export_summary.json`;
- adds crop direct field emission estimates;
- exports DFE-augmented crop tables and uncertainty tables;
- writes immutable stage `03-05` snapshots and appends validated run records to `outputs/pipeline_run_manifest.json`.

The crop DFE stage currently supports the committed summary outputs present in the repo, especially:

- `summary_province`
- `summary_region`
- `summary_crop_national`
- `summary_crop_group_national`
- `summary_cropping_system`

### 7.5 Notebook 3 livestock: livestock DFE augmentation

`notebooks/3_livestock_espac_direct_field_emissions.ipynb`:

- reads the filtered livestock summary selected in `outputs/02_latest_livestock_filtered_export_summary.json`;
- applies the current exploratory livestock DFE logic;
- exports DFE-augmented livestock tables and uncertainty tables;
- writes immutable stage `03-05` snapshots and appends validated run records to `outputs/pipeline_run_manifest.json`.

The livestock DFE outputs retain the routed animal-input columns from notebook 2. This keeps the animal technosphere basis explicit in the DFE-augmented CSVs and avoids later reuse of one generic live-weight value across several animal exchanges.

The livestock DFE branch is explicitly exploratory and proxy-heavy. It is operational, but its outputs should still be documented carefully as a developing component.

Latest consistency update:

- the milk lifetime constant in notebook 3 was aligned with notebook 2's 5.5-year setting;
- `MILK_PRODUCTIVE_LIFE_LACTATIONS` is now `6.581967213114754` (equivalent to 5.5 years at 305 days per lactation);
- synthetic-summary notes now report approximately 6.6 lactations of 305 days for milk headcount calculations.

### 7.6 Notebook 4: crop exchange roundtrip

`notebooks/4_exchange_grid_roundtrip.ipynb`:

- prepares crop exchange review tables;
- supports matching foreground exchanges to background datasets;
- interacts with the helper scripts in `scripts/`.

Important helper scripts include:

- `scripts/nb04_process_name_matcher.py`
- `scripts/nb04_xml_exchange_table_tool.py`
- `scripts/fix_simapro_reference_categories.py`
- `scripts/fix_simapro_reference_exchange_comment.py`

This stage is still partly manual and is the least automated part of the crop workflow.

### 7.7 Notebook 5 crops: crop XML generation

`notebooks/5_crops_espac_lci_xml_generator.ipynb`:

- reads crop DFE outputs;
- applies the crop XML template and exchange mapping logic;
- writes XML files for the supported crop summary levels;
- appends stage `05_xml` lineage records to `outputs/pipeline_run_manifest.json`.

The current crop XML naming scheme uses labeled record parts plus a numbered strategy tag. For example, files are now written as:

- `00001_group_forages_pastures_strategy_8.xml`
- `00001_group_cereals_strategy_8.xml`
- `00007_group_vegetables_strategy_8.xml`

### 7.8 Notebook 5 livestock: livestock XML generation

`notebooks/5_livestock_espac_lci_xml_generator.ipynb`:

- reads livestock DFE or filtered livestock LCI outputs;
- applies the livestock XML templates;
- uses the routed `Animal_input_*_live_weight_kg_per_1kg_product` columns when populating animal technosphere exchanges;
- writes livestock XML files to `outputs/05_xml_exports_livestock_lci/summary_province/`;
- writes livestock XML files to `outputs/05_xml_exports_livestock_lci/summary_region/` when the region strategy is selected;
- writes livestock XML files to `outputs/05_xml_exports_livestock_lci/summary_national/` when the national strategy is selected;
- appends stage `05_xml` lineage records to `outputs/pipeline_run_manifest.json`.

Current livestock XML outputs now use semantic filenames. Examples include:

- `product_cattle_live_aggregation_national.xml`
- `product_donkey_live_aggregation_national.xml`
- `product_eggs_aggregation_national.xml`
- `product_goat_live_aggregation_national.xml`
- `product_horse_live_aggregation_national.xml`
- `product_meat_poultry_aggregation_national.xml`
- `product_milk_aggregation_national.xml`
- `product_mule_live_aggregation_national.xml`
- `product_ovine_live_aggregation_national.xml`
- `product_swine_live_aggregation_national.xml`

## 8. Current methodological features reflected in the repo

### Crop side

The crop workflow currently includes:

- crop and cultivated-pasture extraction;
- grouping at several geographic and product levels;
- YAML-driven yield and coefficient logic;
- crop DFE augmentation;
- crop XML export currently committed for `summary_cropping_system`, `summary_crop_group_national`, `summary_crop_national`, `summary_province`, and `summary_region` summaries.

Permanent-system SOC handling is now integrated into the crop DFE and crop XML chain through the current DFE configuration file. Some coefficients are still proxies and should be treated as provisional rather than Ecuador-specific final parameters.

### Livestock side

The livestock workflow currently includes:

- species/product-specific extraction from ESPAC livestock modules;
- proxy completion for diet, water, electricity, and output normalization;
- CSV-stage routing of concerned animal inputs for livestock XML exchanges;
- cattle pasture linkage logic;
- exploratory livestock DFE augmentation;
- livestock XML export at `summary_province`, `summary_region`, and `summary_national` levels.

Current livestock national behavior:

- there is only one active national livestock strategy, based on the integrated V2 workflow;
- livestock national aggregation keeps system types separate by default;
- the optional combination of livestock system types into one national result is user-controlled in the marimo app and CLI (`--combine-systems`), not automatic.

Recent milk-method change reflected in outputs:

- milk cow live-weight amortization now uses `producing_years_ec = 5.5` years;
- the current national milk XML dairy-cow exchange (`dairy cow, at farm {BR} Economic, U`) reflects this update and the 3.76% dairy-cow economic allocation factor in `outputs/05_xml_exports_livestock_lci/summary_national/product_milk_aggregation_national.xml`.

Recent egg-method change reflected in outputs:

- laying-hen live weight and hen feed now use `producing_years_ec = 1.5` years;
- reported ESPAC egg counts are treated as weekly counts and annualized with `output_periods_per_year = 52` before shell-egg kg conversion;
- the current national egg XML laying-hen exchange (`laying hen <17 weeks, at farm {RER} Economic, U`) reflects this update in `outputs/05_xml_exports_livestock_lci/summary_national/product_eggs_aggregation_national.xml`.
- the current national egg XML artificial-area occupation/transformation exchanges use the non-cage layer-house area proxy in `outputs/05_xml_exports_livestock_lci/summary_national/product_eggs_aggregation_national.xml`.

Current livestock animal-input routing:

- `cattle_live` -> `calf, at farm {BR} Economic, U`, with cattle stock/outflow age factor and 6.73% economic allocation applied in notebook 2
- `swine_live` -> `piglet, at farm {BR} Economic, U`, with swine stock/sales age factor and 93.72% economic allocation applied in notebook 2
- `meat_poultry` -> `one-day-chicken, at farm {BR} Economic, U`, with 100% economic allocation applied in notebook 2; uncertainty bounds use aggregate live-weight/reference-output ranges because the current product summary has no usable poultry sales/outflow basis
- `goat_live` -> `kid goat, conventional, intensive forage area, at farm gate {FR} U`; uncertainty bounds use aggregate live-weight/reference-output ranges because no goat sales/outflow field is available in `oenac`
- `ovine_live` -> `kid goat, conventional, intensive forage area, at farm gate {FR} U`, with ovine stock/outflow age factor applied from `gvnac` stock and `vgonac.total` sales/outflow
- `milk` -> `dairy cow, at farm {BR} Economic, U`, with 3.76% economic allocation applied in notebook 2
- `eggs` -> `laying hen <17 weeks, at farm {RER} Economic, U`, with 100% economic allocation applied in notebook 2

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
8. ESPAC does not directly provide a single dairy-cow productive-life variable; the current milk-cow age proxy uses a weighted stock/outflow estimator and an explicit policy-constrained parameter choice (`producing_years_ec = 5.5`).
9. Crop pipeline now applies an Ecuador-centered plausibility cap for fermented organic fertilizer before aggregation and uncertainty generation: `Organic_fermentado_kgha` is clipped at `20,000 kg/ha` at row level in notebook 2, and downstream `Total_fert_org_kgha`, grouped min/max uncertainty bounds, and XML exchanges inherit the capped value.

Examples of major proxy-dependent areas include:

- irrigation requirements and efficiencies;
- fertilizer composition assumptions;
- pesticide active-ingredient allocation;
- crop residue and SOC parameters;
- livestock diet completion;
- livestock compound-feed proportionality to routed animal-input exchanges;
- livestock water and electricity use;
- livestock live-weight and FPCM normalization;
- routed livestock animal input proxies, including the current use of the kid-goat process for both goat and ovine live-animal product rows; no separate kid-goat economic allocation factor is currently applied because no explicit factor has been supplied;
- cattle, swine, and ovine routed animal-input uncertainty now reflects ESPAC stock/outflow variation through `Animal_input_age_related_factor`; goat routed kid-goat and meat-poultry one-day-chicken uncertainty use aggregate live-weight/reference-output bounds when no usable sales/outflow basis is available. Extreme upper bounds can occur where reported annual outflow is very small relative to stock, so these bounds should be interpreted as empirical screening ranges rather than fitted confidence intervals;
- rare crop rows can still contain unit-consistent but agronomically implausible organic entries; the `Organic_fermentado_kgha` cap is a conservative safeguard and should be reviewed if Ecuador-specific crop guidance is tightened by crop type or agroecological zone;
- direct field emission factors imported from non-Ecuador literature.

## 10. Diagnostics and supporting reports

Important tracked report outputs include:

- `reports/05_ecuador_pesticide_method_note.md`
- `reports/05_legacy_input_requirements_report.csv`
- `reports/05_xml_uncertainty_audit_report.csv`

The crop XML readiness report remains relevant because some legacy template expectations are still only partially populated even though the current operational export path works for the committed XML outputs.

## 11. Reproducibility notes

The project is notebook-backed and app-assisted rather than orchestrated by a single monolithic CLI pipeline. Reproducibility currently depends on:

- stable folder structure;
- consistent notebook execution order;
- consistent marimo app selections when the app is used as the operational interface;
- manifest-backed immutable snapshots and run records in `outputs/pipeline_run_manifest.json`;
- stable input filenames in `inputs/`;
- correct use of the local `.venv` environment;
- manual care during crop exchange review when notebook 4 is used.

The current setup scripts improve reproducibility compared with earlier repo versions by standardizing environment creation, Jupyter kernel registration, and marimo launch behavior.

### 11.1 Required run sequence for complete notebook 6 availability

To make a configuration available as a complete, selectable run in notebook 6:

1. run notebook 2 export for the target branch/summary/filter set;
2. run notebook 3 for that same configuration (this produces stage `03-05` DFE snapshots used by notebook 6);
3. optionally run notebook 5 to generate XML and stage `05_xml` lineage records.

If several notebook 2 runs are executed, notebook 3 must be run for each configuration that should appear as a complete DFE run in notebook 6.

## 12. Recommended citation metadata

When citing outputs from this repository, record at minimum:

- ESPAC survey year: `2024`
- branch used: `crop` or `livestock`
- summary level used: for example `region`, `crop_national`, `crop_group_national`, `cropping_system`, `province`, or `national`
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
- `notebooks/7_espac_lcia_poster_storyboard.ipynb`
- `inputs/02-05_espac_lci_coefficients.yml`
- `inputs/03-05_dfe_factors.yml`
- `reports/05_ecuador_pesticide_method_note.md`
- `reports/05_legacy_input_requirements_report.csv`
- `reports/05_xml_uncertainty_audit_report.csv`

## 14. LCIA storyboard and figure-generation layer (Notebook 7)

`notebooks/7_espac_lcia_poster_storyboard.ipynb` is now the dedicated figure-building and traceability layer for the LCIA poster/report workflow. It consumes `outputs/ESPAC LCIA.xlsx` plus summary CSV inventories and generates cleaned comparative figures and indexed traceability tables.

### 14.1 Current figure outputs

Notebook 7 currently generates (or refreshes) figure families under:

- `outputs/reports/figures_lcia_poster/`

Main families currently include:

- ESPAC fingerprint visualizations
- regional/province comparison visualizations
- cross-database comparisons for eggs and milk
- individual tropical crop impact-vs-yield visualizations
- uncertainty and supporting comparative plots

### 14.2 Current technical behavior reflected in latest implementation

1. Source labeling in comparisons now uses `Product n:` keys from the LCIA workbook structure, not metric-name heuristics.
2. `Ecuador_needs` is explicitly interpreted as source `ESPAC` with geography `EC`.
3. Comparison plot labels are rendered as source-plus-geography (for example `ESPAC (EC)`, `Agri-footprint (RER)`, `AGRIBALYSE (FR)`, `ecoinvent (GLO)`).
4. Regional-differences labeling was cleaned to remove `crop, region` and `crop, province` wording from plot-facing text.
5. Individual tropical crop extraction in Notebook 7 is aligned to the workbook row convention used in this project state:
   - crop names from line 90
   - impact values from line 91
6. Negative-impact crop points are explicitly listed and filtered before concerned visualization stages that request non-negative impacts only.
7. Yield axis behavior for concerned crop scatter views now supports log scaling with positive-value handling.
8. Permanent-crop markers in the combined crop scatter are visually differentiated with black outlines.
9. Bubble/marker sizing in concerned crop scatter views is proportional to crop-level `n`.
10. Crop-level `n` matching for Notebook 7 is resolved from crop-level references (including datapoint-count tables) and no group-level fallback is used for crop-level labels where strict crop-level counts are required.

### 14.3 Current generated report artifacts from Notebook 7

Notebook 7 writes/refreshes supporting report tables in:

- `outputs/reports/7_lcia_*.csv`

These include cleaned workbook extracts, reference coverage/index tables, and enriched crop-level tables used for figure traceability and QA.

## 15. Documentation maintenance note

`ESPAC_project_documentation.md` should be updated whenever approved implementation changes affect:

- notebook structure;
- input files used by the pipeline;
- exported output sets;
- naming conventions;
- major assumptions or proxy methods;
- setup or reproducibility workflow.

At the current project state, the most important recent developments reflected in this document are:

- the split crop/livestock notebook architecture;
- the marimo app as the operational frontend;
- continued retention of the Jupyter notebooks as the methodological and development backbone;
- committed livestock CSV and XML outputs with semantic filenames;
- the new PowerShell environment/bootstrap workflow;
- the current crop XML naming scheme and committed crop output coverage;
- the removal of the old livestock `product` strategy in favor of a single integrated V2 national path;
- the optional crop and livestock reference-cache layer for preview acceleration.
- the milk-cow productive-life update: ESPAC-based hint calculation plus operational 5.5-year normalization across notebook 2 and notebook 3.
- the Notebook 7 LCIA storyboard layer, especially source-label mapping, crop-point extraction conventions, and figure rendering rules.
