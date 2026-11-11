# Dataset Selection Memo

**Project:** Multimodal classification of renal cell carcinoma

**Course track:** Cancer Detection — tumor subtype classification

**Date:** September 27, 2026

**Status:** Proposed design; matched cohort availability has not yet been audited.

## 1. Cancer question and biological motivation

Can integrating diagnostic H&E histopathology images and tumor RNA expression improve patient-level classification of clear cell, papillary, and chromophobe renal cell carcinoma compared with either modality alone? Selected clinical variables will be evaluated as an additional source of information.

These histologic subtypes have distinct tissue morphology and molecular characteristics. The biological hypothesis is that image features and gene-expression programs capture complementary aspects of tumor differentiation and metabolism. Pathway-based expression features may help interpret the molecular contribution. Improvement from combining modalities is a hypothesis to test, not an assumed outcome.

This project falls under the course's Cancer Detection track but specifically addresses classification of established tumors. It does not evaluate screening or early cancer detection, and it will not establish clinical readiness.

## 2. Candidate datasets and unit of observation

### Primary data sources

| Source | Role in the project | Link |
| --- | --- | --- |
| TCGA-KIRC | Clear cell kidney cancer cohort; candidate pathology, expression, and clinical data | [GDC project](https://portal.gdc.cancer.gov/projects/TCGA-KIRC) |
| TCGA-KIRP | Papillary kidney cancer cohort; candidate pathology, expression, and clinical data | [GDC project](https://portal.gdc.cancer.gov/projects/TCGA-KIRP) |
| TCGA-KICH | Chromophobe kidney cancer cohort; candidate pathology, expression, and clinical data | [GDC project](https://portal.gdc.cancer.gov/projects/TCGA-KICH) |
| Pan-kidney study, Ricketts et al. (2018) | Reviewed subtype annotations and initial patient roster, particularly supplementary Table S1 | [Article and supplements](https://pmc.ncbi.nlm.nih.gov/articles/PMC6075733/) |

The Pan-kidney study analyzes the underlying TCGA patients; it is not an independent validation dataset. Its annotations will guide cohort selection and label reconciliation, while the selected input files will be obtained through GDC. Project membership alone will not be treated as definitive histologic ground truth.

### Unit of observation

The unit of observation is **one patient's selected primary renal tumor**. Each modeling example will have one reviewed subtype label and its associated image, expression, and clinical inputs.

A patient may contribute several slides, with many image patches extracted from each slide. These patches are not independent patient observations. Associated image information will be aggregated for patient-level prediction, and all slides, patches, and molecular samples from a patient will remain in the same validation partition.

Patient identifiers will align modalities. Specimen metadata will also be checked: a patient match does not establish that the slide and RNA were obtained from the exact same tissue section. Rules for selecting among multiple tumor samples or slides will be documented before modeling.

## 3. Expected X and y, and approximate scale

**X** denotes the predictors supplied to the model. **y** denotes the subtype the model should predict.

| Component | Proposed definition |
| --- | --- |
| X: imaging | Features extracted from diagnostic H&E whole-slide images, aggregated by patient |
| X: molecular | Primary-tumor RNA expression, potentially reduced to selected genes or pathway scores |
| X: clinical | Selected available variables, initially age at diagnosis and sex |
| y: target | Reviewed histologic subtype: clear cell, papillary, or chromophobe |

The Pan-kidney publication reports 843 tumors: 488 clear cell, 274 papillary, and 81 chromophobe. These are publication-cohort counts, not confirmed counts with every required modality. The expected modeling scale is hundreds of patients, subject to a metadata audit and quality checks. Finer historical subtype annotations, ambiguous cases, and label disagreements will be handled using predefined mapping and exclusion rules.

RNA profiles initially contain thousands of gene measurements. Whole-slide images require feature extraction and may yield many patches per patient. Final patient counts, feature dimensions, usable slide counts, and storage requirements remain to be determined. Image patch counts will not be reported as the number of independent observations.

### Cohort assembly

1. Extract patient identifiers and reviewed subtype annotations from the Pan-kidney supplements.
2. Query GDC for file and specimen metadata covering diagnostic slides, primary-tumor expression, and clinical records.
3. Match patients, reconcile labels, and identify eligible cases with the required modalities.
4. Generate filtered manifests and download the selected files.
5. Assign patient-level validation partitions before constructing training examples; process modalities and align their features by patient.

All learned preprocessing, imputation, feature selection, and dimensionality reduction will be fitted within training partitions. The cohort documentation will preserve file identifiers, GDC release, retrieval date, label sources, and inclusion/exclusion decisions.

## 4. Proposed evaluation metrics

Metric preferences updated October 27, 2026.

Evaluation will compare image-only, RNA-only, and combined models using the same patients and validation partitions. Clinical inputs will be evaluated as an extension. Initial models will use pretrained image features and regularized classifiers or simple prediction fusion, rather than training a large image model from scratch.

| Metric | Purpose |
| --- | --- |
| **Macro-F1 — primary** | Calculate F1 separately for each subtype, then take the unweighted mean. This gives each subtype equal weight and balances precision with recall. |
| Per-class precision and recall | Quantify false-positive and false-negative behavior for each subtype, including the smaller chromophobe class. |
| Per-class Average Precision (AP) | Evaluate each subtype one-versus-rest using continuous class scores; report subtype prevalence alongside AP. |
| Per-class ROC-AUC | Evaluate each subtype one-versus-rest using predicted class probabilities. |
| Confusion matrices | Report patient counts and row-normalized percentages to show which subtypes are confused. |

Macro-F1 reduces majority-class dominance by weighting subtypes equally, but an average can still conceal poor performance on an individual subtype. Per-class secondary metrics are therefore essential. AP and ROC-AUC will use probabilities before argmax, not hard class predictions. Model selection will use development-set Macro-F1. The main comparison is whether multimodal integration improves Macro-F1 over the strongest single-modality model on held-out patients. Failure to improve is still an informative finding about the added value of the modalities.

## 5. Major bias and confounding risks

| Risk | Potential consequence | Planned response |
| --- | --- | --- |
| Patient leakage | Related slides or patches in training and testing inflate apparent performance | Split by patient and keep all associated records together |
| Collection-site or processing effects | The model learns staining, scanner, or RNA-batch differences associated with subtype | Inspect site/batch distributions and evaluate across sites where feasible |
| Class imbalance | Larger subtype groups can dominate training and overall accuracy | Use Macro-F1 for model selection; report per-class precision, recall, AP, ROC-AUC, and confusion matrices; evaluate class weighting using development data and document tradeoffs |
| Missing-modality selection | Patients with complete inputs differ from excluded patients | Document exclusions and compare available characteristics of included and excluded cases |
| Label inconsistency | Project codes disagree with reviewed diagnoses | Reconcile labels using the Pan-kidney annotations and document unresolved cases |
| Direct target leakage | Diagnosis fields, project codes, or filenames reveal the answer | Exclude these fields from predictive features |
| Specimen mismatch | Imaging and RNA represent different tumor regions or specimens | Check specimen metadata and document the limits of matching |
| Limited generalizability | Performance within TCGA does not transfer to other populations or specimen settings | Limit conclusions to retrospective classification in the evaluated cohort |

If published gene signatures derived from this same cohort are used, their role will be identified as exploratory. They do not provide independent validation of biological findings or model performance.

## 6. Backup dataset and fallback scope

**Candidate backup dataset: TCGA-BRCA (Breast Invasive Carcinoma).** A possible alternative is PAM50 molecular-subtype prediction from pathology images and DNA methylation, with selected clinical variables and published subtype annotations. Matched availability must be established before adopting this design.

- [TCGA-BRCA GDC project](https://portal.gdc.cancer.gov/projects/TCGA-BRCA)
- [TCGA breast publication, sample lists, and PAM50 resources](https://gdc.cancer.gov/about-data/publications/brca_2012)

Switching to breast cancer would require revising the biological question, target definitions, and input modalities. PAM50 labels are expression-derived, so predicting them from RNA expression partly reproduces the label-generating process and should not be presented as independent subtype discovery. Handling of normal-like, missing, or conflicting labels would also need to be defined.

Within the kidney project, a smaller fallback is to retain imaging and RNA while omitting clinical predictors if clinical completeness is inadequate. This is a scope adjustment, not a separate backup dataset. Clinical missingness should not unnecessarily reduce the core imaging-plus-RNA cohort.

## 7. Immediate feasibility check

The next deliverable is a patient-level availability table linking reviewed subtype labels to eligible diagnostic slides, primary-tumor RNA files, and clinical completeness. It will establish the final cohort size and class balance before large downloads or model development.

Additional source descriptions and access links are recorded in [DATA_SOURCES.md](DATA_SOURCES.md).

## Reference

C. J. Ricketts et al., “The Cancer Genome Atlas comprehensive molecular characterization of renal cell carcinoma,” *Cell Reports*, vol. 23, no. 1, pp. 313–326.e5, Apr. 2018, doi: [10.1016/j.celrep.2018.03.075](https://doi.org/10.1016/j.celrep.2018.03.075).
