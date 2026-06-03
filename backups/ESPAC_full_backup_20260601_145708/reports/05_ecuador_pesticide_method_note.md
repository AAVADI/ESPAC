# Ecuador dominant pesticide molecules by crop (estimated)

## Output file
- `ecuador_dominant_pesticides_by_crop_estimated.csv`
- 40 crops x 5 molecules (200 rows), percentages sum to ~100% per crop over top-5 only.

## How percentages were built
1. Crop-level pesticide class shares (insecticide/herbicide/fungicide) were calculated from `espac_crop_lci_table_filtered_dfe.csv`.
2. Active ingredients were assigned by crop profile using Ecuador/Andean literature and registration context.
3. Within each pesticide class, literature-informed molecule weights were combined with ESPAC class shares.
4. Top-5 molecules per crop were selected and renormalized to 100%.

## Key sources used
- FAO AGRIS index + full text (Ecuador tomato producers; reports molecules including metamidophos, chlorpyrifos, mancozeb, carbofuran):
  - https://agris.fao.org/search/en/providers/122620/records/647758c23c68d546031f4da8
  - https://revistas.unl.edu.ec/index.php/agropecuaria/article/download/1040/994/2807
- FAO AGRIS index (Ecuador banana/cacao fungicide review; includes mancozeb and systemic fungicides):
  - https://agris.fao.org/search/en/providers/122413/records/647469a5bf943c8c7980234c
- INIAP Ecuador technical note (rice weed control; references propanil and atrazine use in rice systems):
  - https://repositorio.iniap.gob.ec/handle/41000/1407
- AGROCALIDAD (Ecuador regulatory context and updates to active ingredient restrictions/cancellations):
  - https://www.agrocalidad.gob.ec/restriccion-del-uso-de-plaguicidas/
- Market/registration context for Ecuador active ingredients (used only as supporting signal, not as sole evidence):
  - https://news.agropages.com/News/NewsDetail---50006.htm

## Important caveat
- There is no single public Ecuador dataset with measured *molecule-level* use shares by crop across all 40 ESPAC crops.
- Therefore, these shares are **literature-constrained estimates** (not direct sales/application measurements).
- For audited shares, use AGROCALIDAD registration + import/sales microdata by crop and province.
