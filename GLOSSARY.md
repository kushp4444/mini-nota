# Mini-Nota

Mini-Nota is a demonstration of a cohort imaging workflow using public, de-identified Lung1 patient data. It presents scan checks, tumor masks, radiomic features, and survival-model results alongside a record of the workflow's actions and decisions.

## Language

**Run**:
A single execution of the imaging workflow for a selected group of patients, including its results and recorded decisions.

**Selected cohort**:
The patients chosen by the user when starting a run.

**Eligible cohort**:
The selected patients with usable scan-derived features who can receive risk scores. A missing outcome record prevents evaluation, but does not itself prevent scoring.

**Evaluation cohort**:
The patients whose risk scores and outcome records support evaluation. Patients omitted from evaluation are identified with their exclusion reasons.

**Flagged patient**:
A patient whose scan triggers the anonymization QC alarm and is excluded from further processing in that run.

**Patient processing failure**:
A failure of a patient's scan checks, mask construction, or feature extraction that prevents that patient from continuing in the run. The patient and reason are shown to the user and recorded in the run's audit log.

**Survival join exclusion**:
A patient omitted from evaluation when their features and outcomes cannot be combined into a usable record, with the patient's identity and reason explicitly recorded. This does not itself prevent scoring when usable features exist.
_Avoid_: Silent drop

**Human gate**:
A pause before survival scoring that requires approval to proceed after a patient flag, processing failure, or evaluation exclusion.

**Development cohort**:
The patients used to choose model settings through cross-validation and fit the final model. These patients are not offered for selection in the demo.

**Held-out patient**:
A patient reserved before model development, whose data is not used to fit the model or select its settings. The demo's selectable library consists of these patients.

**Risk score**:
A model output used to order patients by predicted risk, not a survival probability or predicted lifespan. With fixed measurements and model version, a patient's score does not change when the selected cohort changes.

**Reference cohort**:
The fixed development cohort whose score distribution provides context for individual risk scores. It is separate from the held-out cohort used to evaluate model performance.

**Risk percentile**:
A patient's position in the reference cohort's score distribution. It expresses relative model risk, not the probability of death, and does not change when the selected cohort changes.

**Agent panel**:
The visible record of a run's plan, tool calls, results, decisions, approvals, and outcome.

**Run history**:
The runs and saved results available in the user's current browser. If that local history is unavailable, the user must start a new run.
