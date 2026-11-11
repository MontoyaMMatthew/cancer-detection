# Data sources for multimodal tumor subtype classification

Last reviewed: September 27, 2026.

## Recommended dataset: TCGA renal cell carcinoma

The proposed project combines diagnostic H&E histopathology images, tumor RNA expression, and selected clinical variables to classify clear cell, papillary, and chromophobe renal cell carcinoma. Assemble the cohort from the three TCGA projects below. This is classification of established tumors, not screening or early cancer detection.

TCGA is the research program; the NCI Genomic Data Commons (GDC) is the main source for its molecular, clinical, biospecimen, and digitized pathology data. These are related data collections, not a single ready-to-train multimodal download. Patient-level overlap and usable sample counts must be established before modeling.

### TCGA-KIRC — Kidney Renal Clear Cell Carcinoma

Contains the clear cell renal cell carcinoma cohort. Use its eligible primary-tumor RNA expression profiles, diagnostic pathology slides, and clinical records as one component of the three-class dataset. Reconcile project membership with curated histologic labels before assigning the target.

- [GDC project page and data access](https://portal.gdc.cancer.gov/projects/TCGA-KIRC)
- [Original TCGA clear cell study and supplemental data](https://gdc.cancer.gov/about-data/publications/kirc_2013)

### TCGA-KIRP — Kidney Renal Papillary Cell Carcinoma

Contains the papillary renal cell carcinoma cohort. Retrieve the same modalities as for KIRC. For the initial project, use a curated broad papillary class rather than attempting finer historical papillary subdivisions; inspect ambiguous or reclassified cases explicitly.

- [GDC project page and data access](https://portal.gdc.cancer.gov/projects/TCGA-KIRP)
- [Pan-kidney study with pathology review and supplemental annotations](https://pmc.ncbi.nlm.nih.gov/articles/PMC6075733/)

### TCGA-KICH — Kidney Chromophobe

Contains the chromophobe renal cell carcinoma cohort. It contributes the third class and is smaller than the other two cohorts, making per-class evaluation important. Its distinct mitochondrial and metabolic characteristics provide biological motivation for integrating morphology and expression.

- [GDC project page and data access](https://portal.gdc.cancer.gov/projects/TCGA-KICH)
- [NCI summary of the TCGA chromophobe study](https://www.cancer.gov/ccg/research/genome-sequencing/tcga/studied-cancers/chromophobe-renal-cell-carcinoma-study)

### Pan-kidney publication cohort — subtype labels and cohort curation

Ricketts et al. (2018), *The Cancer Genome Atlas Comprehensive Molecular Characterization of Renal Cell Carcinoma*, describes a pathology-reviewed cohort of 843 tumors: 488 clear cell, 274 papillary, and 81 chromophobe. These are publication-cohort totals, not current GDC project totals or confirmed counts with matched imaging, RNA, and clinical data.

Use the article's supplemental information, particularly Table S1, as a starting point for patient annotations and label reconciliation. Project codes alone should not be assumed to be definitive histologic diagnoses. Record the label source and handling of disagreements or exclusions.

- [Full article and supplementary materials](https://pmc.ncbi.nlm.nih.gov/articles/PMC6075733/)
- [Publication DOI](https://doi.org/10.1016/j.celrep.2018.03.075)

## What to retrieve from GDC

Select the three kidney projects in the [GDC Data Portal](https://portal.gdc.cancer.gov/), then identify the following data products.

| Component | Recommended selection | Purpose |
| --- | --- | --- |
| Histopathology | Slide Image files, selecting diagnostic H&E slides and checking slide metadata and quality | Tissue morphology input |
| Transcriptomics | Transcriptome Profiling → Gene Expression Quantification → STAR - Counts; eligible primary-tumor samples | Molecular input; processed outputs include counts and normalized expression |
| Clinical | Clinical records, initially age at diagnosis and sex where available | Optional additional predictors |
| Biospecimen metadata | Case, sample, specimen, and file identifiers | Match modalities and exclude inappropriate specimens |
| Curated annotations | Pan-kidney publication supplements | Reference subtype labels |

Prefer open-access processed data for this capstone. Check each file's access designation; controlled-access files require authorization. Raw sequencing reads are not needed for the proposed expression-based workflow.

- [TCGA resources available in GDC](https://gdc.cancer.gov/support/gdc-webinars/tcga-resources-available-gdc)
- [GDC STAR - Counts documentation](https://docs.gdc.cancer.gov/Encyclopedia/pages/STAR_Counts/)
- [GDC RNA expression processing and output descriptions](https://docs.gdc.cancer.gov/Data/Bioinformatics_Pipelines/Expression_mRNA_Pipeline/)
- [GDC data access processes and download tools](https://gdc.cancer.gov/access-data/data-access-processes-and-tools)

Match by case identifier, then verify sample and specimen compatibility. A patient match does not guarantee that the slide and RNA came from the same tissue section. Preserve this distinction in the cohort documentation. Keep all samples and slides from each patient within the same model-validation partition.

Before downloading large image collections, produce an availability table containing patient ID, curated subtype, eligible slide files, eligible RNA files, and clinical completeness. Save the GDC release, retrieval date, file manifest, and inclusion/exclusion decisions. Do not use project codes, diagnosis fields, or filenames as predictive features.

## Alternative dataset: TCGA-BRCA — Breast Invasive Carcinoma

TCGA-BRCA is an alternative if the intended target is a molecular subtype rather than a histologic subtype. Candidate targets are PAM50 Luminal A, Luminal B, HER2-enriched, and Basal-like classes. Candidate inputs include histopathology, DNA methylation or copy-number profiles, and selected clinical variables. Establish matched availability before selecting modalities.

PAM50 labels are derived from gene expression. Predicting them using RNA expression partly reproduces the label-generating process; it should not be presented as independent molecular-subtype discovery. Specify a consistent published label source and define how normal-like, missing, or conflicting labels are handled. The 2012 publication resource represents a historical data freeze, not necessarily every case now in GDC.

- [GDC TCGA-BRCA project page and data access](https://portal.gdc.cancer.gov/projects/TCGA-BRCA)
- [TCGA breast study, sample lists, and PAM50 resources](https://gdc.cancer.gov/about-data/publications/brca_2012)

## Optional radiology datasets: TCIA kidney collections

These collections provide radiology for subsets of TCGA patients. They are alternatives if the course requires CT or MRI as the imaging modality. They are separate from the diagnostic histopathology slides recommended above. Match TCIA patient identifiers to GDC cases and re-audit the available cohort; radiology coverage does not imply matched molecular data for every case.

| Collection | Description | Dataset webpage |
| --- | --- | --- |
| TCGA-KIRC | Radiology for a subset of clear cell kidney cancer patients; the collection lists CT, MR, and CR | [TCIA TCGA-KIRC](https://www.cancerimagingarchive.net/collection/tcga-kirc/) |
| TCGA-KIRP | Radiology associated with the papillary kidney cancer cohort | [TCIA TCGA-KIRP](https://www.cancerimagingarchive.net/collection/tcga-kirp/) |
| TCGA-KICH | CT and MR for a small subset of chromophobe kidney cancer patients | [TCIA TCGA-KICH](https://www.cancerimagingarchive.net/collection/tcga-kich/) |

Additional collection descriptions are available through the Imaging Data Commons: [KIRC](https://portal.imaging.datacommons.cancer.gov/collections/tcga_kirc/), [KIRP](https://portal.imaging.datacommons.cancer.gov/collections/tcga_kirp/), and [KICH](https://portal.imaging.datacommons.cancer.gov/collections/tcga_kich/). Follow the dataset-specific citation and usage information on the collection pages.

## Program overview and discovery pages

These pages explain the broader resources; they are not individual dataset downloads.

- [NCI TCGA program overview](https://www.cancer.gov/ccg/research/genome-sequencing/tcga)
- [NCI cancer genomics data access overview](https://www.cancer.gov/ccg/access-data)
- [GDC Data Portal](https://portal.gdc.cancer.gov/)

## Current status

This document identifies candidate sources and the recommended cohort design. No patient-level overlap audit or dataset download has been completed. Final cohort size, class balance, clinical completeness, and usable slide counts remain to be verified.
