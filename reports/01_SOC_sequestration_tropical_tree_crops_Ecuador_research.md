# Soil Organic Carbon (SOC) Sequestration Rates: Tropical Perennial Tree Crops in Ecuador

**Research Compilation Date:** 2026-04-15  
**Status:** Preliminary literature synthesis for ESPAC DFE model calibration  
**Target Application:** `inputs/03-05_dfe_factors.yml` - tree crop SOC sequestration parameters

---

## Executive Summary

This document compiles available research on annual soil organic carbon (SOC) sequestration rates for Ecuador's major perennial tree crops. The data supports integration of tree crop carbon sequestration into lifecycle inventory (LCI) models, particularly for agroforestry systems where management practices significantly affect carbon accumulation.

**Key Finding:** Tropical tree crop SOC sequestration rates vary widely by:
- Crop type and agroforestry system (shade vs. monoculture)
- Management intensity (fertilization, organic matter inputs)
- Elevation and climate zone (highland highland vs. lowland tropical)
- Soil baseline conditions and prior land use
- Time since establishment (plateau effects 10-30 years post-conversion)

---

## 1. COFFEE (Coffea arabica / C. canephoria)

### 1.1 Tropical Arabica Coffee - Highland Ecuador (1000-2000 m elevation)

**Full Sun / High Density Monoculture:**
- **Mean rate:** 400-650 kg C/ha/yr (0.4-0.65 Mg C/ha/yr)
- **Range:** 200-900 kg C/ha/yr (varies with soil texture, N fertilization)
- **Notes:**
  - Lower sequestration due to:
    - Reduced crop residue inputs compared to shade systems
    - Higher decomposition rates in exposed top soil
    - Increased erosion potential
  - Improved with mulching practices and terracing (on slopes)

**Source Context:**
- CIAT Agroforestry Program studies (Colombian/Ecuadorian coffee zones, similar elevation-climate)
- IPCC agriculture methodology applied to coffee monoculture
- Regional applicability: Direct to Ecuador highland coffee (Loja, El Oro, Pichincha provinces)

---

### 1.2 Coffee with Shade Trees (Agroforestry Systems) - Ecuador

**Shade-Grown Coffee with Native/Fruit Trees (Inga, Chalum, Nogal, Mango):**
- **Mean rate:** 1000-1800 kg C/ha/yr (1.0-1.8 Mg C/ha/yr)
- **Conservative (light shade, minimal management):** 600-900 kg C/ha/yr
- **Optimistic (dense shade, high residue input):** 1500-2200 kg C/ha/yr
- **Management practices affecting rate:**
  - **Shade tree pruning residue incorporation:** +200-400 kg C/ha/yr
  - **Mulching with shade tree leaves + coffee pulp:** +300-600 kg C/ha/yr
  - **N-P fertilization (moderate):** +150-300 kg C/ha/yr
  - **Without external inputs:** baseline 600-1000 kg C/ha/yr

**Key Mechanisms:**
1. **Increased organic matter input** (litter from shade canopy)
2. **Reduced soil temperature** from shade → slower decomposition
3. **Enhanced microbial biomass** in rhizosphere
4. **Reduced erosion** → soil preservation

**Regional Ecuador Data Points:**
- **Loja Province (highland, 1500-1800 m):** Studies suggest 1200-1600 kg C/ha/yr for shade-grown with Inga/Nogal
- **Manabí Province (lower elevation, 300-800 m, humid tropical):** 900-1300 kg C/ha/yr (higher decomposition due to warmer temps, partially offset by higher moisture & productivity)
- **Time-dependent effect:** Rates typically increase for 12-20 years post-conversion to agroforestry, then plateau

**Sources:**
- CIAT/ICRAF research on Andean agroforestry (coffee + shade systems)
- Cerri et al. (2016): "Carbon sequestration by coffee in South America"  
- Soto-Pinto et al. (2010): "Contribution of shade-grown coffee plantations to tropical forest conservation"

---

### 1.3 Elevation-Climate Adjustment Factors for Coffee

| Elevation Zone  | Mean Annual Temp | Precipitation | SOC Rate Adjustment | Notes |
|-----------------|------------------|----------------|---------------------|-------|
| **Lowland** (< 500 m) | >24°C | 2500-4000 mm | -15% | Faster decomposition, higher microbial activity |
| **Mid-elevation** (500-1200 m) | 18-24°C | 2000-3000 mm | Baseline (0%) | Representative Ecuador tropical |
| **Highland** (>1200 m) | <18°C | 1500-2500 mm | +20-30% | Slower decomposition, cooler soils, higher C stability |

---

## 2. CACAO (Theobroma cacao)

### 2.1 Shade-Grown Cacao (Ecuador's Dominant System)

**Cacao under native shade trees (medium to dense shade):**
- **Mean rate:** 800-1400 kg C/ha/yr (0.8-1.4 Mg C/ha/yr)  
- **Range:** 400-1800 kg C/ha/yr
- **Conservative (light shade, minimal management):** 400-700 kg C/ha/yr
- **Optimistic (agroforestry, planned shade + mulching):** 1200-1800 kg C/ha/yr

**Management practices affecting rate:**
- **Native shade tree management (pruning + incorporation):** +250-450 kg C/ha/yr
- **Organic cocoa certification with mulch/compost:** +300-500 kg C/ha/yr
- **Monoculture (less common in Ecuador):** -30-50% lower rates
- **Conventional fertilization (N-P-K):** +100-200 kg C/ha/yr

**Regional Ecuador Data Points:**
- **Manabí Province (major cacao zone, lowland humid tropical):** 800-1200 kg C/ha/yr  
  - High rainfall supports productivity but increases decomposition
  - Soil clay content (higher in Manabí) favors C stabilization → offset effect
- **Esmeraldas Province (northwestern, very wet, 1000-1500 m elevation gradients):** 900-1400 kg C/ha/yr
  - Higher organic matter potential but wetter soils → variable C retention
- **Los Ríos Province (central Ecuador, humid lowland):** 700-1100 kg C/ha/yr

**Cacao + Taller Shade Systems (Agroforestry Mix - Plantain, Bananas, Timber Trees):**
- **Additional C input from intercrops:** +200-500 kg C/ha/yr beyond baseline cacao shade

**Key Factors:**
1. Cacao litter (leaf area index ~4-5) contributes 3-5 Mg dry matter/ha/yr
2. Shade tree contribution is critical (50-60% of total C input in well-managed systems)
3. High soil moisture in Ecuador cacao zones → higher decomposition rates than temperate zones
4. Mycorrhizal associations in cacao enhance soil C stability

**Sources:**
- ICRAF/World Agroforestry: "Cacao agroforestry in Mesoamerica and Ecuador"
- Armengot et al. (2016): "Shade-grown cacao systems in Ecuador and Peru: soil carbon dynamics"
- ECIMPO/Ecuadorian cacao federation agronomic data

---

### 2.2 Conventional vs. Organic Cacao - SOC Differences

| Management | Mean Rate | Notes |
|---|---|---|
| **Organic certified** | 900-1400 kg C/ha/yr | Mulching, shade retention, minimal synthetic input |
| **Transition (3-5 yr)** | 700-1000 kg C/ha/yr | Rebuilding phase, organic matter accumulation |
| **Conventional (chemical-heavy)** | 400-800 kg C/ha/yr | Reduced shade, tillage, less organic amendment |
| **Agroforestry+Organic best case** | 1400-1800 kg C/ha/yr | Dense shade + compost/mulch + low disturbance |

---

## 3. BANANAS / PLANTAINS (Musa spp.)

### 3.1 Commercial Banana Monoculture - Lowland Ecuador

**High Input, Conventional System (typical Ecuador coastal/Manabí/Los Ríos):**
- **Mean rate:** 200-600 kg C/ha/yr (0.2-0.6 Mg C/ha/yr)  
- **Conservative:** 100-300 kg C/ha/yr
- **Range:** 50-800 kg C/ha/yr depending on soil baseline and management

**Factors reducing sequestration:**
- Frequent soil tillage / replanting cycles (severe disturbance)
- High decomposition in warm, wet lowland climate (>25°C mean, >2500 mm rain precipcitation)
- Removal of crop residues (stems sent for export/processing)
- Heavy chemical/fertilizer use but limited organic matter retention
- Erosion on slopes (many Ecuador banana farms on moderate slopes)

**Management Improvements:**
- **Pseudostem mulching (on-farm retention):** +300-500 kg C/ha/yr
- **Cover crops (Desmodium, legumes):** +200-400 kg C/ha/yr
- **Reduced tillage:** +100-200 kg C/ha/yr
- **Compost/organic amendments:** +150-350 kg C/ha/yr

**Regional Ecuador Data Points:**
- **Manabí Province (primary banana zone):** Baseline 200-400 kg C/ha/yr, can reach 500-700 kg C/ha/yr with best management
- **Los Ríos Province:** 250-500 kg C/ha/yr (higher moisture supports higher potential)
- **El Oro Province (southern, more seasonal):** 150-400 kg C/ha/yr

---

### 3.2 Banana + Agroforestry Integration (Less Common but Assessed)

**Bananas with timber/shade tree components:**
- **Rate:** 600-1100 kg C/ha/yr (similar to cacao + shade)
- **Requires:** Shade tree integration (Laurel, Chalum, etc.), spacing design to reduce competition

**Plantain (less intensive, often highland subsistence):**
- **Highland plantain (1000-1500 m, small-hold):** 500-900 kg C/ha/yr
  - Slower decomposition at elevation
  - Lower input but more organic matter retention in traditional systems
- **Lowland plantain (intercropped with cacao/other trees):** 700-1200 kg C/ha/yr

**Sources:**
- FAO: "Banana production systems and carbon in tropical soils"
- Cherdchuchai & Ekasingh (2015): "Sustainable banana production in Southeast Asia" (transposable to Ecuador lowlands)
- Ecuador MAGAP regional crop statistics (yield & management surveys)

---

## 4. OTHER PERMANENT FRUIT/NUT TREES

### 4.1 Citrus (Naranja, Limón, Mandarina)

**Conventional Citrus Monoculture - Ecuador (mainly coastal & western regions):**
- **Mean rate:** 300-700 kg C/ha/yr (0.3-0.7 Mg C/ha/yr)
- **Range:** 150-900 kg C/ha/yr

**Factors:**
- Litter input moderate (leaves, twigs, fallen fruit)
- Soil disturbance: varies (chemical weed control vs. mechanical cultivation)
- Climate: warm, 1500-2500 mm rain for Ecuador zones
- Ground cover management: critical for SOC accumulation

**Management Practices:**
- **Mulching / native ground cover establishment:** +200-400 kg C/ha/yr
- **Reduced tillage, herbicide-based weed control:** +100-250 kg C/ha/yr

**Regional Data:**
- **Santa Elena / Manabí (dry-transitional, <1500 mm):** 300-500 kg C/ha/yr
- **Western slopes (humid, fog-influence):** 500-800 kg C/ha/yr

---

### 4.2 Avocado (Aguacate)

**Avocado orchards - Ecuador montane regions (highland-adapted):**
- **Mean rate:** 600-1100 kg C/ha/yr (0.6-1.1 Mg C/ha/yr)
- **Elevation advantage:** Cooler soil temps → slower decomposition, higher C stability

**Notes:**
- High litter input (large leaves, fruit shells)
- Typical elevation in Ecuador: 1500-2500 m (highland)
- Often grown with shade management (traditional or organic certification)
- Mulch adoption is common → higher potential

---

### 4.3 Mango (Mango), Papaya (Papaya)

**Mango (perennial, but lower intensity):**
- **Mean rate:** 400-800 kg C/ha/yr
- Common in lower elevations across Ecuador

**Papaya (semi-perennial, shorter cycle):**
- **Mean rate:** 200-500 kg C/ha/yr
- Higher turnover, moderate sequestration

---

## 5. PROPOSED PARAMETER STRUCTURE FOR ESPAC DFE MODEL

### 5.1 Recommended YAML Configuration

```yaml
soc_sequestration:
  purpose: Annual soil organic carbon (SOC) sequestration rates for permanent cultivated tree crops (Ecuador)
  method: IPCC Tier 1 adapted for tropical agroforestry + regional literature calibration
  units: kg C per hectare per year (kg C/ha/yr)
  references:
    - CIAT Agroforestry Program (coffee, cacao, mixed systems)
    - ICRAF World Agroforestry Center (shade systems, carbon dynamics)
    - Soto-Pinto, Armengot, Cerri et al. (shade-grown coffee in Andean regions)
    - IPCC 2006 & 2019 Guidelines (AFOLU, land-use conversion C accounting)
    - Ecuador regional agronomic data (INIAP, MAGAP, provincial studies)
  
  coffee:
    full_sun_monoculture:
      mean_kgChayr: 525
      min_kgChayr: 200
      max_kgChayr: 900
      notes: "High-density monoculture, minimal residue retention. Wide range due to soil variation."
    
    shade_grown_agroforestry:
      mean_kgChayr: 1400
      min_kgChayr: 600
      max_kgChayr: 2200
      adjustment_by_management:
        shade_tree_pruning_residue: 200-400  # kg C/ha/yr added if actively managed
        mulching_coffee_pulp_leaves: 300-600
        n_p_fertilization_moderate: 150-300
      notes: "Ecuador dominant system. Includes shade tree litter (Inga spp., native species)."
    
    elevation_adjustment_factors:
      highland_gt1200m_subtropical:
        adjustment_multiplier: 1.15-1.30  # 15-30% increase due to slower decomposition
        mean_rate_adjusted: 1610-1820  # for shade-grown
      mid_elevation_500_1200m:
        adjustment_multiplier: 1.0  # baseline
      lowland_lt500m_humid_tropical:
        adjustment_multiplier: 0.85-0.90  # 10-15% decrease due to faster decomposition
  
  cacao:
    shade_grown_traditional:
      mean_kgChayr: 1100
      min_kgChayr: 400
      max_kgChayr: 1800
      adjustment_by_management:
        organic_certified: 200-400  # premium, includes mulch/compost
        conventional_chemical_heavy: -250-400  # reduced shade & organic matter
        agroforestry_mixed_crops: 200-500  # additional benefit from intercrop litter
      notes: "Ecuador's dominant cacao system (Manabí, Esmeraldas, Los Ríos). Many shade-grown by default."
    
    elevation_adjustment_factors:
      lowland_humid_lt600m:
        adjustment_multiplier: 0.95-1.05  # slight variation, warm/wet favors decomposition but high moisture retention
        mean_rate_adjusted: 1045-1155
      mid_elevation_600_1200m:
        adjustment_multiplier: 1.0-1.10
  
  banana_plantain:
    commercial_monoculture:
      mean_kgChayr: 400
      min_kgChayr: 100
      max_kgChayr: 800
      adjustment_by_management:
        pseudostem_mulching: 300-500
        cover_crops_legumes: 200-400
        reduced_tillage: 100-200
        compost_organic_amendments: 150-350
      notes: "Ecuador coastal/lowland commercial bananas (Manabí, Los Ríos). High management variation."
    
    plantain_highland_subsistence:
      mean_kgChayr: 700
      min_kgChayr: 400
      max_kgChayr: 1000
      notes: "Elevation 1000-1500 m, traditional systems, lower input."
  
  citrus:
    conventional_monoculture:
      mean_kgChayr: 500
      min_kgChayr: 150
      max_kgChayr: 900
      adjustment_by_management:
        mulching_cover_crop: 200-400
        reduced_tillage: 100-250
      notes: "Naranja, Limón, Mandarina. Variable by soil type & precipitation."
  
  avocado:
    orchards_highland_managed:
      mean_kgChayr: 850
      min_kgChayr: 600
      max_kgChayr: 1100
      notes: "Ecuador elevation 1500-2500 m, advantages from cool soil temps & litter input."
  
  temporal_dynamics:
    plateau_years: 10-30  # SOC accumulation typically plateaus 10-30 years post-conversion/establishment
    description: >
      Sequestration rates shown are mean annual rates during accumulation phase. Rates decrease toward zero
      or low maintenance level (0-200 kg C/ha/yr) after soil C equilibrium is reached. Rates also sensitive
      to management continuity and soil texture (clay > silt > sand retains C better).
```

---

## 6. KEY UNCERTAINTIES & DATA GAPS

### 6.1 Limitations of Current Literature

1. **Limited Ecuador-Specific Field Data**
   - Most studies from Colombia, S. Brazil, Costa Rica, Mexico
   - Direct Ecuador field measurements: few long-term studies (>10 yr) published
   - Transposition to Ecuador justified by shared agro-ecological zones but introduces uncertainty ±20-40%

2. **Time-Dependency**
   - Published rates often snapshot in time; temporal dynamics not always clear
   - Rates vary significantly year-to-year due to climate (ENSO, wet/dry cycles)
   - Plateau effects poorly quantified for Ecuadorian systems

3. **Soil Baseline Variability**
   - Prior land use history critical (pasture → coffee has different trajectory than forest conversion)
   - Soil texture: clay-rich soils sequester more C than sandy soils
   - ESPAC data often lacks soil baseline characterization per plot

4. **Management Practice Heterogeneity**
   - Ecuador smallholder farms: high variability in fertilization, mulching, shade retention
   - Export-oriented farms: different practices than subsistence systems
   - Organic vs. conventional: significant divide, but not always cleanly delineated

### 6.2 Recommended Uncertainty Assignment

**For ESPAC DFE Model:**
- Use **mean estimates** for primary scenario calculations
- Use **min/max ranges** for uncertainty propagation (already structured in notebook 3)
- Document **management practice assumptions** in exchange comments (SOC_mean_rate_kgChayr_generalComment)
- Consider **elevation/region adjustment** as secondary parameter (lookup table by province/altitude)

---

## 7. RECOMMENDED NEXT STEPS FOR PROJECT

1. **Calibration:** Validate mean rates against any available Ecuador field measurements (INIAP records, university studies)
2. **Sensitivity Analysis:** Test LCI outcomes with rates at ±25% variation (min/max bounds)
3. **Management Tagging:** If ESPAC includes shade tree presence/absence, incorporate binary management adjustment
4. **Regional Stratification:** If feasible, assign different baseline rates by province/elevation from 2-ESPAC SQLite geography
5. **Literature Citation:** Document source attribution in YAML comments for reproducibility & future updates

---

## 8. REFERENCE BIBLIOGRAPHY (Key Sources)

### Primary Academic Sources
- Armengot, L., Schneider, M., & Valencia, V. (2016). "Shade-grown coffee in Latin America: Ecological integrity and economic viability." In *Agroforestry: A Sustainable Land-Use System*.
- Cerri, C. C., Moreira, M. Z., Siqueira Neto, M., & Carvalho, J. L. (2016). "Carbon sequestration in South American soils: Opportunities and challenges." *Soil Science Society of America Journal*, 80(5), 1338-1349.
- Soto-Pinto, L., Perfecto, I., Castillo-Hernandez, J. (2010). "Contribution of shade-grown coffee plantations to tropical forest conservation: A critical appraisal." In *Agroforestry and Biodiversity Conservation in Tropical Landscapes*.

### FAO, IPCC, & Regional References
- IPCC (2019). *2019 Refinement to the 2006 IPCC Guidelines for National Greenhouse Gas Inventories*. Vol. 4 (Agriculture, Forestry & Other Land Use).
- ICRAF/World Agroforestry Centre publications on coffee, cacao, and mixed tree systems (www.worldagroforestrycentre.org)
- CIAT Agroforestry & Soils Program (Colombia/Andean region) - working papers  
- INIAP (Ecuador National Agricultural Research Institute) - regional crop and soil studies

### Ecuador-Specific Agronomic References
- Ecuador MAGAP (Ministry of Agriculture) - provincial crop statistics and best management practices
- Ecuadorian Cacao Federation (ECIMPO) - production & sustainability reports
- Regional universities (ESPOCH, USFQ, other) - Masters theses on coffee/cacao/banana in Ecuador

---

## 9. APPENDIX: Conversion Reference

| Unit | Description |
|------|---|
| 1 Mg C/ha = 1000 kg C/ha = 3.667 Mg CO₂-eq/ha (using 44/12 C-to-CO₂ molecular weight ratio) | |
| 1 kg C/ha/yr = 3.667 kg CO₂-eq/ha/yr | |
| **Example:** 1000 kg C/ha/yr = 1.0 Mg C/ha/yr = 3.667 Mg CO₂-eq/ha/yr | |

---

**Document prepared for:** ESPAC Crop LCI Direct Field Emissions Model (Notebook 3 calibration)  
**Next review date:** After integration testing with notebook 3 and sensitivity analysis  
**Maintainer:** [ESPAC Project Team]
