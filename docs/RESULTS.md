> Current release: see [ROBUSTNESS.md](ROBUSTNESS.md). Serving uses the balanced word/character candidate with automatic routing disabled. Earlier model-selection and routing measurements below describe the original release.

# Evaluation and benchmark record

All numbers below come from saved, executed runs. Test fixtures are never used to produce evaluation files. Full machine-readable reports contain per-class precision/recall/F1, confusion matrices, representative errors, calibration bins, Brier scores and complete coverage/error curves.

## Protocol

Bitext CSV at commit `72ea2203180d14a416b579c657033ecd21e59a11`, SHA-256 `6f81102b0100b97b8468eb04368033a23206bf1fde9d53500d5806ec1001a434`. Seed 42. Exact normalization/deduplication and stateless char-gram graph grouping precede five-fold stratified group assignment. All 23,619 retained rows have source row IDs, group IDs and split assignments in `artifacts/split-manifest.json`. Train/validation/test counts are 12,883 / 4,409 / 6,327. The transitive grouping creates substantial class imbalance; validation INVOICE has eight examples and test SUBSCRIPTION has 33. Aggregate performance must be read alongside per-class support.

Baseline: train-only word 1?2 gram TF-IDF, min document frequency 2, sublinear TF, max 60,000 features; logistic regression C selected from 0.5, 2, 8 by validation macro-F1. BERT: pretrained Google two-layer/128-hidden checkpoint (Apache-2.0), pinned revision `30b0a37ccaaa32f332884b96992754e246e48c5f`; fine-tuned for three CPU epochs, batch 64, AdamW 5e-4, weight decay .01, max length 64. Best epoch selected by validation macro-F1. No hyperparameter/test sweep. PyTorch deterministic algorithms enabled, seed 42 and four threads.

The confidence target is empirical >=98% validation accuracy among >=100 accepted examples, selecting maximum coverage. A 0.50 operational confidence floor was added after the initial test report to allow low-confidence manual review in the demo; the same floor applies to both models. Reports were regenerated from frozen checkpoints with validation selection only; no test-error-specific threshold adjustment occurred. This audit detail is retained to avoid suggesting that the original experiment was fully preregistered.

## Results

| Model | Validation macro-F1 | Test macro-F1 | Test accuracy | Threshold | Test coverage | Test auto accuracy |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 0.996794 | 0.994981 | 0.995258 | 0.50 | 0.985459 | 0.998236 |
| Tiny BERT | 0.999189 | 0.992802 | 0.994942 | 0.50 | 1.000000 | 0.994942 |

Model selection uses the validation >=99% macro-F1 quality floor and then lower warm batch-one CPU median latency, with resource checks. Both qualify; baseline is selected. This sacrifices a small validation score advantage for much lower latency, artifact size and process memory. The baseline also happened to score higher on test, but test was not the selection criterion.

| Model | Train seconds | Artifact bytes | Isolated training-process RSS MiB | Warm median ms | Warm p95 ms | Serial predictions/s |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 5.88 | 523492 | 203.55 | 0.5988 | 0.7499 | 1615.26 |
| Tiny BERT | 282.10 | 18499775 | 783.48 | 4.2877 | 5.7315 | 224.37 |

RSS is a process snapshot from each original separate training process, not a peak or model-only memory estimate. The standalone comparison was remeasured after training ended: five warmups plus 100 serial batch-one requests using validation texts; baseline BLAS threads two, transformer torch threads four. CPU/platform, logical CPUs, RAM, package versions and Python version are recorded in each report. Microbenchmark throughput is reciprocal mean inference time; it is not service throughput.

## Confidence diagnostics

| Model | Ten-bin test ECE | Multiclass test Brier |
|---|---:|---:|
| Baseline | 0.076289 | 0.024665 |
| Tiny BERT | 0.000810 | 0.009698 |

No post-hoc probability calibration was fit. Baseline is often underconfident on easy in-domain samples; the transformer is very confident and has low in-domain ECE. Neither implies reliable confidence under shift. The synthetic demo includes an ambiguous request that the baseline confidently maps to ORDER, illustrating why these numbers do not certify real-ticket safety. Human review only catches low confidence, not all mistakes.

The dashboard includes confidence coverage/error bars using validation rows, matrices and per-class metrics using test rows. Full curves include thresholds 0.000 through 1.000 in increments of .025, with null accuracy/error for zero accepted samples.

## Service benchmark

`python -m scripts.benchmark --count 40 --concurrency 4`: one persistent Windows worker, 40 synthetic requests, eight repeating demo texts, four concurrent clients, .05-second polling, one-second dispatch scan, no concurrent training. HTTP results are awaited through terminal persisted status. All 40 completed without terminal failure; manual-review results count as completed, not errors.

Elapsed 9.6274 seconds; throughput 4.1548 tickets/second.

| Stage | Median ms | p95 ms |
|---|---:|---:|
| end_to_end_ms | 1028.9763 | 1070.7509 |
| queue_wait_ms | 930.4965 | 973.7714 |
| inference_ms | 2.9293 | 3.3066 |

Queue wait includes submission-to-claim time, while inference measures predict_proba only. HTTP end-to-end includes DB commits, scheduling, model processing and polling delay. This short, closed-loop benchmark is not saturation load, a distributed load test or a capacity promise. Cold model startup is excluded from the warmed benchmark but API and DB overhead are included. Raw IDs/status/times and environment are in `artifacts/benchmark.json`.

## Verification limits

19 backend/unit/reliability tests passed using a dedicated PostgreSQL database and Redis DB 15; one real Chromium desktop/mobile flow passed against trained inference and persisted routing/review. Frontend TypeScript check and Vite production build passed. Native PostgreSQL 18 and an unofficial Windows Redis 5 port were used for runtime verification; Compose targets PostgreSQL 17 and Redis 7. These specific container versions, Linux fork workers, Docker build/startup and remote GitHub Actions were not run here. A Starlette TestClient deprecation warning is emitted by the installed dependencies; it did not fail tests.

Dataset wording is synthetic and highly templated; source generation-family IDs are absent, so more distant semantic relatedness may remain across splits despite exact/near-duplicate grouping. Group imbalance and small classes increase uncertainty. No claims about real users, real-ticket accuracy, fairness, multilingual behavior, production incidents or scale are supported.
