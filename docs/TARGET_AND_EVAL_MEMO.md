# Target Definition and Evaluation Memo

**Project:** Multimodal renal cell carcinoma subtype classification. **Status:** Proposed plan; final cohort size and class balance await the data audit.

## Checkpoint 1: Target definition

| # | Question | Answer |
| --- | --- | --- |
| 1 | What exactly am I predicting? | The reviewed histologic subtype of an established renal tumor: **clear cell, papillary, or chromophobe**. This is three-class classification, not cancer screening or survival prediction. |
| 2 | For whom / what is one row? | One patient's selected primary renal tumor, with matched pathology and RNA data. Multiple slides or patches contribute to one patient-level prediction; they are not independent observations. |
| 3 | At what time is the prediction made? | At a retrospective analysis point after the tumor tissue has been collected, slides digitized, and RNA expression processed. This does not represent a preoperative prediction or claim that RNA was available before the original diagnosis. The reference diagnosis is withheld from model inputs. |
| 4 | How is the label generated? | Use the Pan-kidney study's reviewed histologic annotations in supplementary Table S1. Define the mapping to the three broad classes before modeling; document exclusions and unresolved labels. Do not infer the label solely from the GDC project code. |
| 5 | When does the outcome occur? | The subtype is an existing property of the sampled tumor, recorded through pathologic classification. **No future outcome window applies**; there is no recurrence or survival follow-up target. |
| 6 | Which features exist before prediction? | Diagnostic H&E image features and primary-tumor RNA-expression features available at the defined analysis point; optionally age at diagnosis and sex. Exclude subsequent treatment, follow-up outcomes, and diagnostic subtype fields. |
| 7 | Could any feature reveal the answer indirectly? | Yes: project codes, diagnosis text, histology codes, filenames, and label-derived annotations may expose subtype. Exclude them from predictors. Audit site/batch effects and prevent the same patient's slides or samples from appearing in different partitions. Histologic morphology itself is an intended input, although the reference label also comes from pathology. |

## Checkpoint 2: Evaluation plan

Metric preferences updated October 27, 2026.

| # | Item | Answer |
| --- | --- | --- |
| 1 | Intended use / prediction question | Test whether combining pathology and RNA improves subtype classification over the strongest single-modality model. This is a retrospective research comparison, not a clinical deployment study. |
| 2 | Unit of prediction and evaluation cohort | One prediction per patient, using an eligible primary tumor from TCGA-KIRC, TCGA-KIRP, or TCGA-KICH matched to reviewed Pan-kidney labels. Compare core models on the same patients with usable images and RNA. Evaluate clinical additions on a common eligible subset with matched baselines. |
| 3 | Class prevalence / event rate | The publication cohort contains 488 clear cell, 274 papillary, and 81 chromophobe tumors out of 843: approximately **57.9%, 32.5%, and 9.6%**. Recalculate counts and proportions after filtering and for each partition; these are cohort proportions, not population prevalence. No time-based event rate applies. |
| 4 | Baseline comparator | Include a training-set majority-class predictor, an image-only classifier using frozen pretrained features, and a regularized RNA-only classifier. Select the strongest single-modality comparator using development data, then compare it with the combined model on the same test patients. |
| 5 | Primary metric + why | **Macro-F1**, the unweighted mean of the three subtype-specific F1 scores. This gives each subtype equal weight and balances precision with recall, reducing majority-class dominance. Use development-set Macro-F1 for model selection. Report the combined model's difference from the selected single-modality baseline, with a paired patient-bootstrap 95% confidence interval on the test set. |
| 6 | Secondary metrics | **Per-class precision, recall, Average Precision (AP), ROC-AUC, and confusion matrices** with counts and row percentages. Compute AP and ROC-AUC one-versus-rest from continuous class probabilities before argmax; use non-interpolated AP rather than trapezoidal PR-AUC. Report class sample sizes and prevalence alongside results. These per-class measures expose subtype-specific errors that an aggregate score can obscure. If a class is absent in an evaluation slice, mark its AP/ROC-AUC undefined rather than substituting a score. |
| 7 | Threshold strategy | Assign the class with the highest predicted probability (**argmax**); no binary 0.5 threshold or abstention rule is planned. Select model settings and any fusion weights using development data only, then freeze the decision rule before testing. |
| 8 | Most consequential FP/FN | Prioritize detecting missed chromophobe cases because the smallest class can be hidden by high overall accuracy. Also inspect false chromophobe predictions and every subtype confusion. Each wrong classification is a false negative for the actual class and a false positive for the predicted class. This is an evaluation priority, not an established ranking of clinical harm. |
| 9 | Subgroups / error slices | Examine errors by true subtype, tissue source site, sex, and age group (below 65 vs. 65 and older), plus slide quality where metadata allow. Report subgroup counts; treat small slices descriptively and do not draw firm conclusions from sparse groups. |
| 10 | Leakage controls + held-out evaluation | Provisionally reserve **20% of patients as a locked, subtype-stratified test set**; use stratified five-fold cross-validation within the remaining 80% for model selection. Confirm class counts support this design before training. Keep all patient records together; fit learned preprocessing and feature selection within training folds; use out-of-fold predictions if fitting a fusion model. Evaluate the locked test set once after selection. Audit pretrained-image-model training data for TCGA overlap; add a site-held-out sensitivity analysis if class coverage permits. |

Publication counts and label source: C. J. Ricketts et al., [*The Cancer Genome Atlas Comprehensive Molecular Characterization of Renal Cell Carcinoma*](https://doi.org/10.1016/j.celrep.2018.03.075), 2018. The Pan-kidney cohort overlaps TCGA and is not an external test dataset.

Related documents: [Dataset Selection Memo](DATASET_SELECTION_MEMO.md) and [Data Sources](DATA_SOURCES.md).
