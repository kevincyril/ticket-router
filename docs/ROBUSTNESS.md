# Robustness investigation and corrective release

**Current serving mode: human review for every new ticket.** A richer classifier and validation-selected abstention policy improved some challenge results, but held-out reliability remained inadequate for automatic routing. The implementation preserves that negative result rather than claiming these failures are solved.

## What caused the reported failures

- `ACCOUNT` describes customer profiles, registration and login/password tasks, not bank balances. In the retained training split, all 1,398 messages containing the word `account` have that label. For the first development example, `account` contributes +2.45 to the baseline Account logit, `my` +0.72 and `my account` +0.62; the learned Account intercept is +1.49. Payment has no positive feature contribution for this wording. `two`, `times` and `left` are outside the train-fitted word vocabulary.
- In training, `money` occurs in 379 Refund examples and no other category. `charged` appears once (Cancel) and `twice` once (Order); both are excluded as standalone baseline features by min_df=2. These examples do not teach duplicate-debit semantics. `purchase` occurs most often in Order. The synthetic data supports lexical shortcuts instead of the broader meaning required by these requests.
- The vague example triggers `something`, contributing +2.37 to the Order logit. There is no vague, unsupported or multi-intent training target. A closed-set softmax always picks one supported category even when the input does not justify one.
- The third request contains competing `payment`, `refund`, and `order` features (+2.70 Payment, +1.75 Refund and +1.93 Order contributions respectively). The low raw probability reflects competing class evidence. Its two actionable intents make review defensible; simply forcing a higher probability would not resolve the taxonomy ambiguity.

The trained tiny BERT did not solve the first two development cases: Account 99.83% and Order 98.82%. It chose Refund at 98.05% for the third. Its pretraining and easy source validation scores did not establish robust intent understanding.

## Refund/Returns taxonomy

The supported dataset category is **REFUND**, with `get_refund`, `check_refund_policy`, and `track_refund` intents. It maps to the invented example team **Returns** in `config/routing.json`. There is no separate dataset category named RETURNS, RETURN, or BILLING. PAYMENT (`payment_issue`, `check_payment_methods`) maps to Billing. Duplicate charging is a payment issue; asking for money back is a refund request. A message can contain both, while this dataset assigns exactly one label per source message. No multi-label truth is claimed for mixed requests; this release requires human review.

## Balance and features

Raw data has 27 intents aggregated into 11 categories. Group-disjoint preprocessing leaves 12,883 train / 4,409 validation / 6,327 source-test rows. Training is imbalanced: Account 2,996; Refund 1,533; Order 1,260; Contact 1,209; Feedback 1,194; Payment 1,188; Delivery 972; Subscription 906; Shipping 813; Cancel 604; Invoice 208. Validation Invoice has just eight rows. Grouping avoids close-template leakage but makes support uneven. Full counts, keyword distributions, taxonomy and development-case feature attributions are in `artifacts/robustness/investigation.json`.

The new candidate uses a FeatureUnion of train-only word TF-IDF (1?2 grams) and character TF-IDF (3?5 grams), plus balanced logistic regression (C=2, seed42). Character features improve morphological/spelling coverage; they do not supply missing semantic knowledge. Class weights address category imbalance. These changes were tested together; no ablation establishes their separate contributions. No user example, challenge text or stored review was added to classifier training. The original transformer checkpoint remains frozen for comparison.

## Frozen evaluation protocol

1. `scripts/freeze_challenge.py` authored and hashed both sets before scoring: 65 challenge-validation cases and 88 challenge-test cases. The three user examples are development cases excluded from both. Scenario wording is varied across splits. Test has 48 clear single-intent paraphrases, 12 vague requests, 12 mixed actionable requests and 16 unrelated requests. All categories appear among the clear cases. Mixed, vague and unrelated inputs are labeled must-review; acceptable category sets for mixed requests are not automatic-routing permissions.
2. The original validation split is partitioned by near-duplicate group parity into calibration and policy subsets. No group crosses these subsets. Scalar temperature is fitted by NLL on the calibration subset only. This data was historically used in original model selection, so it is not a new independent calibration benchmark.
3. A fixed grid of confidence, nearest-example similarity and probability-margin gates is searched using the remaining source validation and challenge validation only. Candidate routing also requires agreement with the nearest train-only TF-IDF example and no conflicting sufficiently supported clause predictions. Clause splitting uses generic sentence/conjunction boundaries, with no sentence-specific or label keyword overrides. The grid and exact selection rule are saved in the protocol and selection artifacts.
4. The selection maximizes challenge validation coverage with >=98% observed accepted accuracy, zero must-review auto routes and >=5 accepts, plus >=98% source policy-validation accepted accuracy with >=100 accepts. This is an empirical development criterion, **not a certified safety guarantee**. Hundreds of policies on 65 authored examples can overfit. The selected richer candidate accepted only 16 validation cases with zero errors; its one-sided 95% binomial lower accuracy bound is 82.9%, far below 98%.
5. The selected bundle and selection SHA were frozen before `ml.robustness_evaluate` opened challenge test. No test-dependent cutoff changes or model reselection followed. The challenge test vetoed automatic deployment; thresholds remain frozen and inspectable. Automatic routing is disabled through a separate operational feature flag. The original source test was already reported previously and is labeled a historical regression check, not untouched new evidence.

This challenge is hand-authored by the implementing assistant, not an independently annotated or representative sample of customer tickets. Semantic design overlap with development concerns is intentional; it tests broader failure types. Audit found no normalized exact overlap with training, challenge validation or the three development examples, and no test/validation character-cosine overlap >=0.85. These checks do not certify semantic independence. Dataset files, hashes, predictions and policy provenance are saved so the limitations are reviewable.

## Actual held-out results

Unsafe auto route = an automatically routed wrong-category clear request OR any automatically routed must-review request. Auto accuracy uses all auto routes as denominator. Coverage and review rate use all 88 requests; the maximum safe coverage for this set is 48/88 because 40 deliberately require review. High-confidence unsafe predictions use probability >=0.80 and include rejected predictions; they are a separate diagnostic.

| Experiment | Unsafe auto routes /88 | Auto coverage | Auto accuracy | Manual review | Clear top-1 accuracy /48 |
|---|---:|---:|---:|---:|---:|
| Original baseline, 0.50 | 18 | 37.5% | 45.5% | 62.5% | 45.8% |
| Original baseline + validation gates | 2 | 6.8% | 66.7% | 93.2% | 45.8% |
| Richer baseline, 0.50 raw (ablation) | 19 | 47.7% | 54.8% | 52.3% | 54.2% |
| Selected richer baseline + gates | 7 | 19.3% | 58.8% | 80.7% | 54.2% |
| Trained transformer, 0.50 | 51 | 87.5% | 33.8% | 12.5% | 60.4% |
| Trained transformer + validation gates | 5 | 17.0% | 66.7% | 83.0% | 60.4% |
| **Deployed review-first mode** | **0** | **0%** | **Undefined: zero automatic decisions** | **100%** | **54.2% model suggestions** |

The selected candidate has 10 correct out of 17 automatic routes. Its 7 unsafe routes comprise two wrong clear categories, one vague request and four mixed requests. It rejects all 16 unrelated cases in this test but that does not certify general OOD detection. The original baseline makes four wrong clear routes plus one vague, nine mixed and four unrelated routes. The original transformer makes 16 wrong clear routes plus ten vague, eleven mixed and fourteen unrelated routes.

The richer classifier improves clear top-1 accuracy from 22/48 to 26/48 (+8.3 percentage points). Frozen BERT gets 29/48, but the deployed candidate was chosen before test and was not replaced after seeing that result. Improved raw classification alone increases unsafe routes from18 to19 by accepting more; gating reduces this to7 at substantial coverage cost. No candidate is presented as reliable automatic routing.

## Calibration under shift

| Model | Historical source-test ECE raw -> scaled | Clear challenge ECE raw -> scaled |
|---|---:|---:|
| baseline | 0.0763 -> 0.0045 | 0.1239 -> 0.2530 |
| improved | 0.0202 -> 0.0007 | 0.1589 -> 0.2374 |
| transformer | 0.0008 -> 0.0049 | 0.3233 -> 0.3558 |

All fitted temperatures reach the lower bound (~0.5), sharpening easy in-domain class distributions. That increases the number of >=80%-score unsafe predictions on challenge cases: baseline8->21, richer baseline7->21, transformer41->51. In-domain calibration therefore **does not transfer under this shift**. ECE is a small-sample bin diagnostic; it is not a bound on individual reliability. Scores remain conditional class scores, not probability that a request is supported or safe to route. The UI displays both raw and scaled scores and an explicit warning.

## Development cases after this release

| Development case | Model suggestion / scaled class score | Experimental candidate gate | Actual deployed action |
|---|---|---|---|
| 1 | ACCOUNT / 94.6% | Review: insufficient_training_support | Review (automatic routing disabled) |
| 2 | ORDER / 98.3% | Route | Review (automatic routing disabled) |
| 3 | PAYMENT / 72.3% | Review: insufficient_training_support, nearest_example_disagrees, conflicting_clause_predictions | Review (automatic routing disabled) |

Cases1 and2 are still category failures. The vague case passes the experimental gate; a global review-first deployment is therefore necessary. Case3 remains Payment, with Refund as an alternative and conflicting clause evidence. Review is not treated as a classification correction. `artifacts/robustness/live-smoke.json` records these requests passing through real HTTP, dispatcher, Redis/RQ, worker and database, all ending in review with no assigned team.

## Implementation and reproduction

New tickets persist `routing_evidence` with raw score, scaled score alternatives, temperature, nearest-training similarity, neighbor agreement, clause conflict, review reasons and candidate routing recommendation. Migration002 adds a nullable JSON column; historical predictions and review decisions remain unchanged. The worker defaults to `AUTO_ROUTING_ENABLED=false` even for a high-score candidate. Explicit experimental opt-in exists, but this experiment does not support enabling it. `/api/model` exposes actual mode; `/api/robustness` serves saved comparisons; the dashboard explains review-first behavior.

Reproduce with the existing trained original artifacts and frozen challenge data:

```powershell
$env:OMP_NUM_THREADS='2'; $env:OPENBLAS_NUM_THREADS='2'
.venv\Scripts\python -m ml.robustness_select
.venv\Scripts\python -m scripts.package_robust_model
.venv\Scripts\python -m ml.robustness_evaluate
.venv\Scripts\python scripts/test_local.py
# Restart to load the new model and migration:
powershell -ExecutionPolicy Bypass -File scripts/stop-local.ps1
powershell -ExecutionPolicy Bypass -File scripts/start-local.ps1
$env:BROWSER_BASE_URL='http://127.0.0.1:8000'
.venv\Scripts\python -m pytest tests/test_browser.py -q
```

Selection never opens challenge test for decisions (only its hash is recorded). Final evaluation never optimizes thresholds or writes selection artifacts. Rerunning an already exposed test does not create a newly untouched evaluation. Do not edit challenge labels/text or tune against these errors and call the same set independent again. To iterate, collect new training/validation material and freeze a new untouched test before scoring it.

Warm serving-candidate latency includes word/character prediction, calibration, support search and clause checks: 2.48ms median / 6.47ms p95 on88 inputs. It excludes HTTP/queue/database time. Hardware/package versions and exact commands are in the saved report.

## Remaining limits

The app now prevents automatic mistakes by requiring review; it has not solved broad customer-intent generalization. The classifier still lacks representative billing paraphrases, explicit unknown/ambiguity training and multi-label supervision. Nearest-neighbor support and clause heuristics can both accept incorrect shortcuts and reject correct paraphrases. A stronger representative labeled dataset, independently annotated ambiguity policy, suitable scope detection and a new held-out evaluation are needed before restoring useful automatic coverage. No single confidence threshold or calibration scalar establishes that readiness. Docker/Compose execution and remote CI remain unverified on this machine; native tests and the real browser flow are verified.
