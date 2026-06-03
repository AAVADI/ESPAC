# SOC Sequestration Rates: Ecuador Tropical Tree Crops - Quick Reference Table

## Summary Table: Annual SOC Rates (kg C/ha/yr)

| Crop | System Type | Mean| Min | Max | Notes |
|------|---|---|----|-----|-------|
| **COFFEE** | |||||
| | Full-sun monoculture | 525 | 250 | 900 | Low residue, fast decomposition |
| | Shade-grown agroforestry | 1400 | 600 | 2200 | **Ecuador dominant**. Native shade trees (Inga, Chalum) |
| | Highland (>1200m) adj. | 1610 | 690 | 2530 | +15% cooler soils |
| | Lowland (<500m) adj. | 1218 | 522 | 1914 | -13% fast decomposition |
| **CACAO** | |||||
| | Shade-grown (Ecuador default) | 1100 | 400 | 1800 | **Ecuador dominant**. Many retain shade naturally |
| | +Organic certification | +250 | +100 | +400 | Mulching, compost, shade management premium |
| | +Agroforestry (intercrops) | +300 | +100 | +500 | Plantains, bananas, timber trees mixed |
| **BANANA** | |||||
| | Commercial monoculture | 400 | 100 | 800 | High disturbance, residues often exported |
| | +Pseudostem mulching | +400 | +250 | +500 | On-farm residue retention |
| | +Cover crops (legumes) | +300 | +150 | +400 | Interrow Desmodium or native legumes |
| | Plantain, highland | 700 | 400 | 1000 | Subsistence, traditional, cooler elevation |
| **CITRUS** | |||||
| | Convention monoculture | 500 | 150 | 900 | Naranja, Limón, Mandarina |
| | +Mulching/cover crop | +300 | +150 | +400 | Ground cover establishment |
| **AVOCADO** | |||||
| | Highland orchards (1500-2500m) | 850 | 600 | 1100 | Large leaves, cool temps favor retention |
| **MANGO** | |||||
| | Conventional orchards | 600 | 300 | 900 | Moderate litter input, lower management intensity |
| **PAPAYA** | |||||
| | Semi-perennial production | 350 | 150 | 600 | Shorter cycle, lower C accumulation |
| **REFERENCE** | |||||
| | Cultivated pasture (existing) | 900 | 300 | 1500 | ESPAC baseline for comparison |

---

## Multi-Use Summary: Key Decision Points for ESPAC Integration

### 1. **Crop Type Classification (from ESPAC 'Crop' field in Spanish)**

**Coffee Group:**
- CAFE, CAFÉ → Use coffee shade-grown baseline (1400 kg C/ha/yr mean)
- If monoculture indicators → Reduce to 525 kg C/ha/yr

**Cacao Group:**
- CACAO → Use cacao shade-grown baseline (1100 kg C/ha/yr mean)
- If organic certified indicator → Add +300 kg C/ha/yr
- If intercropped (polyculture) → Add +300 kg C/ha/yr

**Banana/Plantain:**
- BANANO → Use commercial baseline (400 kg C/ha/yr mean)
- PLATANO → Use highland plantain (700 kg C/ha/yr mean)

**Citrus:**
- NARANJA, LIMON, MANDARINA → Use citrus baseline (500 kg C/ha/yr mean)

**Other Fruits:**
- AGUACATE → Use avocado baseline (850 kg C/ha/yr mean)
- MANGO → Use mango baseline (600 kg C/ha/yr mean)
- PAPAYA → Use papaya baseline (350 kg C/ha/yr mean)

---

### 2. **Elevation Adjustment (if altitude data available)**

| Elevation (m) | Coffee Adjustment | Cacao Adjustment | Other Fruits |
|---|---|---|---|
| <500 (lowland tropical) | ×0.87 (1218 mean) | ×0.98 (1078 mean) | -10% typical |
| 500-1200 (mid-elevation) | ×1.0 (1400 mean) | ×1.0 (1100 mean) | Baseline |
| >1200 (highland) | ×1.15 (1610 mean) | ×1.05 (1155 mean) | +10% typical |

---

### 3. **Management Practice Modifiers (if ESPAC captures)**

| Practice | Effect |
|---|---|
| **Shade tree presence** (for coffee/cacao) | Coffee: +300-400 kg C/ha/yr over monoculture; Cacao: already included |
| **Mulching/residue retention** | +200-400 kg C/ha/yr most crops |
| **Organic certification** | Coffee/Cacao: +200-400 kg C/ha/yr; Banana: +150-300 kg C/ha/yr |
| **Cover crops (legumes)** | Banana/Citrus: +200-300 kg C/ha/yr |
| **Fertilization (N-P-K)** | Coffee: +150-300 kg C/ha/yr if moderate+; Cacao: already priced in |

---

### 4. **Uncertainty Assignment** (for notebook 3 min/max propagation)

**Conservative (Min) Scenarios:**
- Monoculture systems without active management
- Poor baseline soils or recent establishment
- Use lower bound values from table

**High Potential (Max) Scenarios:**
- Well-managed agroforestry with shade/mulch/compost
- Favorable elevation (highland for most, lowland for water-demanding species)
- Mature systems (>15 years) with optimized practices
- Use upper bound values from table

**Central Estimate (Mean):**
- Regional industry standard practice
- Represents realistic farmer adoption level

---

## Conversion Factors for LCI Output

| From | To | Factor |
|---|---|---|
| kg C/ha/yr | Mg C/ha/yr | ÷1000 |
| kg C/ha/yr | kg CO₂-eq/ha/yr | ×(44/12) = ×3.667 |
| Mg C/ha/yr | Mg CO₂-eq/ha/yr | ×3.667 |

**Example:**
- 1000 kg C/ha/yr = **1.0 Mg C/ha/yr** = **3.67 Mg CO₂-eq/ha/yr**
- 400 kg C/ha/yr = **0.4 Mg C/ha/yr** = **1.47 Mg CO₂-eq/ha/yr**

---

## Temporal Dynamics: Important for LCI Model

**Key point:** Rates shown are during **accumulation phase** (years 1-30 post-establishment).

- **Years 0-5:** Rapid accumulation (often 50-100% above mean shown)
- **Years 5-15:** Steady accumulation (rates approach shown mean)
- **Years 15-30:** Continued but slower accumulation (rates may be 80-100% of mean)
- **Years 30+:** Plateau toward equilibrium (rates drop to 0-200 kg C/ha/yr or even negative if degrading)

**For ESPAC LCI:**
- Assume all crops are in "steady-state" accumulation phase (years 5-25) 
- Use shown rates as representative annual average
- If time-to-equilibrium available in crop metadata, apply decay function for mature systems

---

## Regional Applicability Notes: Ecuador Provinces

### **Coffee Zones** (Loja, El Oro, Pichincha, other highlands)
- **Elevation:** Typically 800-2000 m
- **Main system:** Shade-grown with native trees
- **Recommended rate:** Coffee shade-grown highland adjusted = **1600 kg C/ha/yr** (round mean)
- **Uncertainty:** ±600 kg C/ha/yr (600-2200 range)

### **Cacao Zones** (Manabí, Esmeraldas, Los Ríos)
- **Elevation:** 50-400 m, some transitions to 600 m
- **Main system:** Shade-grown, traditional
- **Soil:** Often clay-rich (Vertisols) → favorable C retention
- **Recommended rate:** Cacao shade-grown lowland = **1100 kg C/ha/yr** (standard)
- **Uncertainty:** ±450 kg C/ha/yr (400-1800 range)
- **Adjustment:** If agroforestry/polyculture add +300, if organic add +300

### **Banana Zones** (Manabí, Los Ríos, El Oro coastal)
- **Elevation:** 0-400 m, some moves to hillsides (500-800 m)
- **Main system:** Commercial monoculture, high-input
- **Recommended rate:** Banana commercial = **400 kg C/ha/yr** (low management potential)
- **Uncertainty:** ±300 kg C/ha/yr (100-800 range)
- **Potential with improvements:** Can reach 700-900 kg C/ha/yr with mulch/cover crops

### **Citrus / Mixed Fruit Zones** (Scattered, western slopes, Sierra transitions)
- **Elevation:** 300-1500 m mixed
- **Main system:** Conventional monoculture, variable management
- **Recommended rate:** Citrus = **500 kg C/ha/yr** (medium potential)
- **Avocado (highland):** 850 kg C/ha/yr (if >1200 m)

---

## Data Confidence Assessment

| Crop/System | Confidence | Evidence Basis | Notes |
|---|---|---|---|
| Coffee shade-grown | **Medium-High** | CIAT, peer-reviewed literature, Andean context | Direct Ecuador data limited; inferred from Colombia/Central America |
| Cacao shade-grown | **Medium-High** | ICRAF, peer-reviewed agroforestry studies | Ecuador context well-studied; organic certification effects validated |
| Banana commercial | **Medium** | FAO, regional agronomic data | High variability by management; limited peer-reviewed rates |
| Citrus | **Low-Medium** | Limited literature; FAO estimates | Few specific studies for Ecuador; transposed from temperate/subtropical zones |
| Avocado | **Low-Medium** | Very limited data; estimated from litter/elevation analogues | Growing in Ecuador but little published research |
| Pastry | **Low** | Minimal published field data for Ecuador hillside papaya | Estimated from crop characteristics |

---

## Recommended Implementation Steps in Notebook 3

**Current State:** Notebook 3 computes SOC only for pastures.

**Proposed Extension:**

1. **Load tree crop parameters:**
   ```python
   tree_crop_soc_config = load_yaml('inputs/03-05_soc_sequestration_tree_crops.yml')
   ```

2. **Identify permanent crop rows:**
   ```python
   is_permanent_crop = df['Category'].str.lower() == 'permanent'
   crop_names = df[is_permanent_crop]['Crop'].unique()
   ```

3. **Map crop name to SOC config:**
   ```python
   soc_by_crop = {crop: tree_crop_soc_config.get(crop, {}).get('mean_kgChayr', 0) for crop in crop_names}
   ```

4. **Apply elevation adjustment (if province field available):**
   ```python
   elevation_province_lookup = {'Loja': 'highland', 'ManabÃ­': 'lowland', ...}
   adjustment = elevation_province_lookup.get(df['Province'].iloc[0], 'mid')
   ```

5. **Assign SOC rates to rows & propagate uncertainty:**
   ```python
   df.loc[is_permanent_crop, 'SOC_mean_rate_kgChayr'] = soc_mean
   df.loc[is_permanent_crop, 'SOC_mean_rate_kgChayr__minValue'] = soc_min
   df.loc[is_permanent_crop, 'SOC_mean_rate_kgChayr__maxValue'] = soc_max
   ```

6. **Document in exchange comment:**
   ```python
   df.loc[is_permanent_crop, 'SOC_method'] = 'Tropical tree crop agroforestry model (CIAT/ICRAF)'
   ```

---

## References (Summary)

**Academic & Technical:**
- CIAT Agroforestry Program (Technical Reports)
- ICRAF World Agroforestry Centre (Publications & databases)
- Soto-Pinto et al. 2010, Armengot et al. 2016, Cerri et al. 2016 (peer-reviewed)

**Policy & Methodology:**
- IPCC 2006 & 2019 Guidelines (AFOLU volumes)
- FAO IPCC EFDB (Emission Factor Database)

**Regional (Ecuador/Andean):**
- INIAP (Instituto Nacional de Investigaciones Agropecuarias)
- Ecuador MAGAP (Ministerio de Agricultura)
- Ecuadorian Cacao Federation (ECIMPO)

---

**Table prepared for:** ESPAC Crop LCI Direct Field Emissions (Notebook 3) integration planning  
**Last updated:** 2026-04-15  
**Status:** Ready for integration testing & validation against farmer survey data (if available)
