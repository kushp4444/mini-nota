# Pretrained model with a held-out patient library

Mini-Nota develops a survival-risk model offline using approximately 80% of the usable full Lung1 dataset, with cross-validation restricted to that development cohort. The remaining approximately 20% is reserved before development and becomes the selectable demo library; actual counts depend on dataset quality checks. The chosen model is fit on the development cohort and frozen, so every selected eligible patient receives a score from the same model without having been used to train it.

This replaces the initial 30-patient scope and live survival fitting. The live workflow is QC, mask construction, feature extraction, and survival scoring. A run permits one or more selected patients and defaults to selecting all; the previous 10-patient learning requirement no longer applies. The full held-out evaluation remains visible independently of the selection, while selected-group charts are labeled exploratory.

Patients with processing failures are excluded from scoring. Patients with usable features but missing outcomes can still receive a score and are explicitly excluded from outcome-based evaluation. After exclusions, the human gate approves scoring the remaining eligible patients and discloses evaluation exclusions.

The model version and development/held-out membership are fixed and recorded. The frozen model's score distribution over the development cohort is the fixed reference for individual risk percentiles. A percentile describes position within that reference distribution, not a probability of death or a performance estimate. The held-out cohort remains separate for evaluation.

The development cohort's median score is the fixed threshold for Kaplan–Meier groups: scores strictly above it are labeled higher model risk, and scores at or below it lower model risk. These are relative model groups, not clinical categories. The chart shows observed survival for selected patients with usable outcomes. If only one group is present, show its curve and explain why a two-group comparison is unavailable; do not change the threshold or manufacture a second group.
