# MethodsX Manuscript Draft

## Title

A reproducible workflow for transforming the Ecuadorian ESPAC 2024 agricultural survey into crop and livestock life cycle inventory datasets and ecospold/XML processes

## Abstract

National agricultural surveys contain valuable foreground information for life cycle assessment (LCA), but they are rarely released in a form that can be used directly for life cycle inventory (LCI) modelling. This paper presents a reproducible notebook-based workflow that transforms the 2024 Ecuadorian `Encuesta de Superficie y Produccion Agropecuaria Continua` (ESPAC) into crop and livestock LCI tables and ecospold/XML process files [1]. The workflow imports the official survey delivery into SQLite, harmonizes source tables and variable dictionaries, and then branches into crop and livestock pipelines that construct intermediate inventories, apply explicit rule-based completion where ESPAC lacks direct inventory detail, estimate direct field emissions with documented Tier 1 and literature-derived factors, and export grouped inventories at multiple spatial and product levels.

The method is designed for transparency, traceability, and incremental improvement rather than false completeness. Median aggregation is paired with empirical min-max uncertainty bounds, and proxy layers remain distinguishable from direct survey observations for pasture yields, fuel use, irrigation, fertilizer composition, pesticide active-ingredient allocation, livestock diets, and utility requirements. The resulting workflow offers a practical route for converting national agricultural survey microdata into reviewable foreground LCI datasets in data-constrained contexts.

## Keywords

Life cycle inventory; agricultural survey; Ecuador; ESPAC; crop LCI; livestock LCI; direct field emissions; ecospold XML; uncertainty; reproducible workflow

## Specifications table

| Item | Description |
|---|---|
| Subject area | Environmental science; life cycle assessment; agricultural systems |
| More specific subject area | Transformation of national agricultural survey data into foreground LCI datasets |
| Method name | ESPAC-to-LCI workflow for crop and livestock inventories |
| Name and reference of original method | No single original method was followed end-to-end; the workflow combines survey ETL, rule-based inventory completion, median aggregation, Tier 1 emissions modeling, and ecospold/XML export |
| Resource availability | Notebook-based workflow and method configuration stored in the ESPAC project repository |

## Background

Agricultural LCI development in low- and middle-income contexts is often constrained by the lack of geographically specific farm-level foreground data collected with consistent national coverage. Ecuador's ESPAC survey partially fills that gap, but its raw structure is not suitable for direct LCI use because variables are distributed across multiple thematic modules, several flows are reported only indirectly, and many inventory parameters needed for LCA are absent [1].

Existing LCA studies often describe foreground-data assembly only briefly, even when survey-derived inventories depend on substantial cleaning, harmonization, proxy selection, and export logic. For a MethodsX contribution, the methodological value lies precisely in making those transformation steps explicit, reproducible, and inspectable. The workflow presented here addresses that need by converting ESPAC 2024 into harmonized crop and livestock foreground inventories that can be reviewed as tables, summarized at several aggregation levels, enriched with direct field emissions, and exported as ecospold/XML datasets.

The workflow is intended for transparent foreground modelling, sensitivity analysis, and iterative improvement rather than for claiming that every flow is directly observed in the survey. It is especially suited to contexts where a national agricultural survey exists, but the path from survey microdata to LCI-ready datasets is not yet formalized.

## Value of the method

- Uses an official national agricultural survey as the main source of foreground production data.
- Separates crop and livestock workflows while preserving a shared ETL and documentation structure.
- Keeps direct survey observations, inferred values, and literature-based proxy completions distinguishable in the exported inventories.
- Propagates bounded uncertainty from grouped records into downstream direct field emission tables and XML exchanges.
- Produces machine-readable ecospold/XML inventories that can be reviewed, matched to background databases, and imported into LCA software.

## Method overview

The workflow contains one shared data-ingestion step followed by two parallel analytical branches. The sequence is intended to make each transformation auditable and to keep direct survey observations separate from later completion and emissions-modelling layers:

1. ESPAC raw files and variable dictionaries are imported into an SQLite database.
2. Crop records are transformed into intermediate LCI tables, aggregated, completed where needed, and passed to crop direct field emission modeling.
3. Livestock records are transformed into intermediate LCI tables, aggregated, completed where needed, and passed to livestock direct field emission modeling.
4. Final crop and livestock tables are converted into ecospold/XML datasets.
5. Intermediate exchanges can be exported to a spreadsheet workflow for background-process matching and manual review.

## Method details

The method is organized as a modular workflow rather than as a single conversion script. This structure follows the logic of the source data and allows each stage to be checked independently before the next stage is run.

### 1. Source data ingestion and harmonization

The starting point is the official open-data delivery for ESPAC 2024 [1]. Notebook 1 reads the nested archive structure, imports the raw tables into SQLite, standardizes table names, and stores the available variable dictionaries together with the survey data. The resulting SQLite database acts as the single analytical source for all subsequent processing steps.

This ETL step serves three purposes. First, it converts the original delivery into a persistent relational structure that is easier to query reproducibly than the source spreadsheets and delimited files. Second, it keeps the raw survey modules available without collapsing them prematurely into one denormalized table. Third, it makes the workflow auditable, because later crop and livestock transformations can be traced back to stable table names and survey fields.

### 2. Crop foreground inventory construction

Crop inventories are built from the permanent-crop, transitory-crop, and cultivated-pasture ESPAC modules. These records are mapped into an intermediate LCI table structured around variables needed for foreground agricultural modeling, including cultivated area, yield, sowing and harvest timing where available, irrigation, fuel use, mineral fertilizers, organic fertilizers, pesticide use by class, and seed demand.

Additional descriptors are inferred to support grouping and rule assignment. These include crop type, crop group, and cropping-system categories. The crop branch exports grouped inventories at province, region, crop-national, cropping-system, and crop-group-national levels.

For grouped inventories, numeric variables are aggregated with the median and text variables with the non-null mode. This choice reduces the influence of skewed observations and extreme values while retaining interpretable representative values for each aggregation group. Crop yields are additionally screened through an FAO-informed outlier-capping step before aggregation.

#### 2.1 Cultivated pasture integration

Cultivated pastures are handled inside the crop workflow rather than as a separate livestock-only component. Records from `rel_inec_pcnac` are exported with `Category = cultivated_pasture` and grouped under `Crop_group = forages_pastures`. These rows preserve ESPAC management observations such as area and input use where available.

ESPAC `pcnac` does not report harvested pasture biomass or a direct production variable. For that reason, cultivated-pasture `Yield_kgha` values are filled from the YAML configuration block `crop_yield_proxies.cultivated_pasture` in `inputs/02-05_espac_lci_coefficients.yml`. These values are proxy dry-matter yields used for output normalization and remain explicitly identifiable as such in the exported metadata. Cultivated-pasture rows are also excluded from the general crop yield-fallback logic so that unrelated crop-yield rules are not transferred to pasture systems.

#### 2.2 Crop inventory completion rules

Because ESPAC is a survey and not an LCI database, several crop flows require rule-based completion:

- unit conversions convert survey units such as pounds, quintals, and tonnes into kilograms;
- fuel demand is partly estimated through literature-derived machinery-energy proxies calibrated to Ecuadorian conditions;
- irrigation demand is estimated from ESPAC irrigation-system information combined with crop-water requirement defaults and irrigation-efficiency assumptions following FAO-style crop-water guidance [2];
- seed use is assigned through default rates by inferred crop type when direct observations are absent;
- mineral fertilizer classes are translated into representative fertilizer analyses to estimate elemental nitrogen, phosphorus, and potassium inputs;
- organic fertilizers are simplified into solid manure, fermented or composted materials, and liquid manure-like inputs, with nutrient and trace-metal contents taken from curated median values in the PRO dataset.

#### 2.3 Pesticide active-ingredient allocation

ESPAC reports pesticide use mainly by functional class rather than by active ingredient. The workflow therefore estimates crop-specific molecule shares by combining class-level ESPAC intensities with Ecuadorian and Andean literature, AGROCALIDAD regulatory context, and rule-based crop profiles encoded in the configuration files [3]. These allocations are literature-constrained estimates rather than directly measured molecule shares and should be interpreted as proxy foreground disaggregation.

### 3. Livestock foreground inventory construction

The livestock branch extracts and harmonizes records from the livestock-related ESPAC modules. In the current implementation, `cattle_live` and `milk` are derived from `rel_inec_glnac`, `swine_live` from `rel_inec_gpnac`, `ovine_live` from `rel_inec_gvnac`, `donkey_live`, `horse_live`, `mule_live`, and `goat_live` from `rel_inec_oenac`, and `eggs` from `rel_inec_apnac`.

Notebook 2 livestock converts these module-specific structures into a common livestock LCI table. Aggregated outputs are generated at province, region, and national levels, and an additional product-only national strategy (`product`) is used to produce system-independent national benchmarks for the same livestock product.

As in the crop branch, grouped livestock inventories use the median for numeric variables and the non-null mode for text variables. This keeps aggregation rules consistent across the workflow.

#### 3.1 Feed-intake reconstruction and proxy diets

Cattle and swine use direct ESPAC diet-share variables where available. These shares are converted into approximate absolute feed intensities in `kg/head/day` using configurable intake assumptions stored in `inputs/02-05_espac_lci_coefficients.yml`.

For species whose ESPAC modules do not provide usable ration splits, the workflow applies literature-based proxy diets. In the current implementation this affects eggs, ovine, goats, horses, donkeys, and mules. Direct ESPAC diet fields and proxy diet fields are kept separate in the exports so that users can distinguish observed survey structure from reconstructed rations.

#### 3.2 Cattle-pasture linkage across survey modules

For cattle and milk rows, the workflow links the holding identifier (`Identificador`) across cattle, cultivated-pasture, and land-use modules. This enables the reported cattle pasture share to be partitioned into cultivated pasture, natural pasture, and unmatched residual pasture using holding-level land shares.

Operationally, the cultivated-pasture feed share is calculated as the reported cattle pasture share multiplied by the fraction of linked area recorded in `Pastos cultivados`. The natural-pasture share is derived analogously from linked `PASTO NATURAL` area in the land-use module. Any remaining pasture share is retained explicitly as unmatched residual pasture. Because ESPAC does not provide pasture biomass yield for either cultivated or natural pasture, the absolute pasture-feed mass still depends on the diet-share and intake-assumption layer. The linkage therefore improves source attribution of pasture feed without fully converting pasture supply into an output-measured pasture-product LCI.

The livestock branch also exports a compact national diagnostic table summarizing the share of total cattle pasture feed attributed to linked cultivated pasture, linked natural pasture, and unmatched residual pasture.

#### 3.3 Infrastructure, water, and electricity completion

ESPAC coverage of livestock infrastructure and utilities is limited. The only direct infrastructure field currently used consistently is the cattle and milk milking-system variable `gl_sistema_ordenio`. When ESPAC does not expose a direct field, the workflow populates `Infrastructure_type`, `Infrastructure_source`, `Water_l_head_day`, `Electricity_kWh_head_day`, and provenance notes from the `livestock_infra_water_electricity_proxy_table` in the coefficient file.

Proxy selection follows a priority order of Ecuador-specific sources first, then Latin American or FAO references, and finally broader fallback references when stronger evidence is not yet available.

### 4. Functional-unit normalization

The crop branch remains expressed on the crop inventory basis used by the XML template. In practice, the crop outputs are still most defensibly interpreted as hectare-based foreground management inventories, even when yield proxies are present for reference-product exchange construction.

The livestock branch carries explicit normalization fields so that inventories can be interpreted on a common product basis. Live-animal products are normalized to `1 kg live weight equivalent`. Milk is normalized to `1 kg fat- and protein-corrected milk (FPCM)` using a density-based conversion from liters to kilograms and the IDF FPCM equation with Ecuador default milk composition values [4]. Eggs are normalized to `1 kg shell eggs` using a literature-derived representative egg mass.

These normalization factors are exported through fields such as `Reference_output_kg`, `Reference_output_kg_for_dfe`, `Functional_unit`, `Milk_output_kg_fpcm_day`, and `Egg_output_kg`.

### 5. Direct field emissions

Direct field emissions (DFE) are calculated in separate crop and livestock notebooks after grouped LCI tables have been created.

#### 5.1 Crop direct field emissions and soil organic carbon

The crop DFE workflow applies a rule-based emissions model to the filtered crop summaries using nutrient contents and coefficients from the project YAML files. The method propagates min-max uncertainty by re-running the relevant calculations with minimum and maximum grouped input scenarios.

The crop branch also includes explicit soil organic carbon (SOC) sequestration coefficients for permanent systems. Cultivated pastures grouped under `forages_pastures` receive a FAO-based South America grassland increment coefficient, while permanent tree and plantation crops receive crop-name-based SOC coefficients stored in the DFE configuration. These values are propagated through the crop DFE uncertainty tables and exported to XML as the elementary flow `Carbon, organic, in soil or biomass stock`, together with minimum and maximum bounds.

Several perennial SOC coefficients remain provisional and should be disclosed as such in scientific use. Current interim cases include `MARACUYA`, `TOMATE DE ARBOL`, `PALMITO`, and `OTROS PERMANENTES`, which rely on FAO-first agroforestry proxy logic, `PINA`, which currently uses a conservative near-zero placeholder, and sugarcane, whose coefficient is management-conditional rather than universal.

#### 5.2 Livestock direct field emissions

The livestock DFE workflow operates on the filtered livestock summaries, reads the matching uncertainty tables, and applies Tier 1 defaults from the livestock DFE configuration. The current implementation uses IPCC 2019 and EMEP/EEA 2023 Tier 1 factors for enteric methane, manure-management methane, ammonia, nitrogen oxides, direct and indirect nitrous oxide, and related manure-nitrogen flows [5,6].

Livestock DFE outputs are divided by the stored livestock reference-output basis so that emissions remain expressed per kilogram of normalized reference product. The livestock DFE notebook also produces a synthetic summary table that reports total pasture feed per kilogram of product together with separated contributions from linked cultivated pasture, linked natural pasture, unmatched residual pasture, and proxy forage where applicable.

Across both branches, the current DFE layer should be interpreted as a transparent proxy-based emissions model rather than a fully Ecuador-calibrated national emissions model. It is intentionally modular and remains improvable. One practical next step would be to treat the present workflow primarily as a raw foreground-LCI generator and then route those LCIs into more specialized agricultural LCA environments for direct-emissions handling, for example MEANS-InOut [9] or HESTIA-compatible downstream harmonization and assessment workflows [10].

### 6. Uncertainty representation

Uncertainty is represented empirically rather than through fitted probability distributions. For each aggregation group and each numeric inventory variable, the workflow exports the minimum and maximum values observed within the same group alongside the median value. These ranges are then propagated into downstream DFE tables and finally into XML exchanges as `minValue` and `maxValue` attributes.

This uncertainty treatment is intentionally simple. It captures observed within-group spread and makes that spread portable into later workflow stages, but it should not be interpreted as a statistical confidence interval or a parametric uncertainty model.

### 7. XML generation and background-process mapping

Final DFE-augmented LCI tables are converted to ecospold/XML inventories in separate crop and livestock XML generator notebooks. Each generator maps XML exchanges to LCI columns through the `generalComment` field in the template XML model and writes one XML file per aggregated inventory row. Exchange-level uncertainty bounds are transferred from the matching uncertainty CSVs when available.

Both XML generators apply a set of compatibility corrections required for successful SimaPro import. These include namespace registration, schema-location handling, validation metadata insertion, exchange-location assignment, explicit input and output group tags, unit enforcement for selected exchanges, and protection of the reference-product exchange by removing uncertainty bounds from exchange 1.

The livestock XML generator also supports multiple template routing. It scans the available livestock XML templates and selects the appropriate template for each product row by reading product tokens encoded in template `generalComment` fields.

Background-process mapping for intermediate inputs is supported by a separate exchange-roundtrip workflow. XML exchanges are exported to a spreadsheet table, candidate matches are generated from a combined ecoinvent and Agribalyse process catalog, and final approval of background links remains manual [7,8].

## Method validation and quality control

Validation in the present workflow is based on internal consistency, traceability, and importability rather than on a fully independent external benchmark dataset.

The main quality-control mechanisms are:

- stable ETL into SQLite before any analytical transformation;
- explicit split between crop and livestock notebooks after the shared ingestion stage;
- use of configuration files for coefficients and proxy rules rather than hard-coded hidden constants;
- grouped uncertainty tables written alongside grouped median outputs;
- diagnostic outputs for special logic such as cattle-pasture linkage;
- XML audit outputs and SimaPro-focused compatibility corrections to ensure generated datasets remain importable.

This validation strategy is suitable for a MethodsX contribution because the main methodological contribution is the transparent conversion of survey data into LCI-ready datasets under incomplete information. The workflow is therefore validated primarily by reproducibility of transformations, consistency of grouped outputs, transparency of proxy assignments, and successful XML importability. The present DFE layer should be viewed as an operational first implementation rather than as the endpoint of methodological development. Future validation can extend this base by comparing selected inventory intensities with Ecuador-specific expert datasets, measured farm studies, or alternative regional LCI sources where available, and by benchmarking the current DFE results against specialized agricultural LCA tools or harmonized data pipelines such as MEANS-InOut or HESTIA-oriented workflows [9,10].

## Limitations and appropriate use

The method combines direct survey observations with explicit rule-based and literature-based completion layers. It should therefore be used as a transparent foreground-data construction workflow, not as evidence that all output variables are directly measured by ESPAC.

The main crop limitations concern fuel demand, irrigation requirements, fertilizer composition, pesticide active-ingredient disaggregation, some DFE parameters, and the lack of direct harvested-output data for cultivated pastures. The main livestock limitations concern ration completion for several species, infrastructure and utility completion outside dairy systems, and reliance on generalized Tier 1 emissions factors. Live-animal outputs are currently represented on a live-weight-equivalent basis rather than slaughter-yield or processed-product basis.

These limitations do not prevent use of the workflow for exploratory LCA, foreground dataset creation, hotspot screening, or sensitivity analysis. They do require clear disclosure whenever the resulting inventories are used in scientific manuscripts, comparative studies, or public decision-support contexts. In particular, users should report which flows are survey-derived, which are inferred from deterministic completion rules, and which depend on external proxy coefficients. Users should also disclose that the current direct field emissions treatment is a project-level implementation that could later be replaced or complemented by more specialized handling after raw LCIs are generated, including in platforms such as MEANS-InOut or in HESTIA-compatible data pipelines [9,10].

## Data and code availability

The operational workflow is notebook-driven and stored in the ESPAC project repository. Reproducing the method requires the ESPAC 2024 source delivery, the project notebooks, and the YAML configuration files used for proxy rules and coefficients. Core components include:

- ETL notebook for importing ESPAC 2024 into SQLite;
- separate crop and livestock notebooks for LCI construction;
- separate crop and livestock notebooks for DFE modeling;
- exchange-roundtrip tools for spreadsheet-based review and background matching;
- separate crop and livestock XML generator notebooks;
- YAML configuration files containing proxy rules, coefficients, nutrient contents, and metadata defaults.

Representative outputs include grouped crop and livestock CSV files, matching uncertainty tables, diagnostic tables, and ecospold/XML exports organized by summary strategy.

## References

[1] INEC, Boletin Tecnico Encuesta de Superficie y Produccion Agropecuaria Continua (ESPAC) 2024, Instituto Nacional de Estadistica y Censos, Ecuador, 2025.

[2] R.G. Allen, L.S. Pereira, D. Raes, M. Smith, Crop evapotranspiration: Guidelines for computing crop water requirements, FAO Irrigation and Drainage Paper 56, Food and Agriculture Organization of the United Nations, Rome, 1998.

[3] AGROCALIDAD, Agrocalidad controla el uso adecuado de insumos agricolas, Agencia de Regulacion y Control Fito y Zoosanitario, Ecuador, 2019.

[4] IDF, The IDF global carbon footprint standard for the dairy sector, Bulletin of the International Dairy Federation No. 520/2022, International Dairy Federation, 2022.

[5] IPCC, 2019 Refinement to the 2006 IPCC Guidelines for National Greenhouse Gas Inventories, Intergovernmental Panel on Climate Change, 2019.

[6] EEA, EMEP/EEA air pollutant emission inventory guidebook 2023, EEA Report 06/2023, European Environment Agency, 2023.

[7] ecoinvent, ecoinvent version 3.12, ecoinvent Association, Zurich, 2025.

[8] ADEME, AGRIBALYSE 3: la base de donnees francaise d'ICV sur l'agriculture et l'alimentation, Agence de la transition ecologique, 2023.

[9] MEANS platform, LCA inventory with Means-InOut, INRAE and CIRAD, https://means.inrae.fr/eng/emc-tools/lca-inventory-with-means-inout, 2025 (accessed 19 April 2026).

[10] HESTIA Community, HESTIA developer and user community, https://community.hestia.earth/, 2026 (accessed 19 April 2026).
