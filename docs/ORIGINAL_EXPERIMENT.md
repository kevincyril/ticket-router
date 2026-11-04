# Historical implementation record

This records the original release. Its automatic-routing configuration and source-dataset results are historical. Current serving behavior and robustness findings are in README.md and docs/ROBUSTNESS.md.

# Relay · support-ticket classification and routing

A running portfolio service: FastAPI + Pydantic + SQLAlchemy/PostgreSQL, Redis/RQ workers, reproducible sklearn and PyTorch/Hugging Face training, and a React/TypeScript dashboard. Submit a synthetic request, follow processing, inspect its raw prediction and team assignment, and resolve uncertain cases in a manual-review queue. Feedback is stored separately and never triggers training.

## Launch

**This workspace is already installed, trained, migrated and built.** On this Windows machine, run from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-local.ps1
```

Open **http://127.0.0.1:8000** (dashboard), **http://127.0.0.1:8000/docs** (interactive API), and `/api/health/ready`. The launcher uses the isolated PostgreSQL cluster on port 55432 and workspace Redis on 56379. It launches API, dispatcher and supervised worker with hidden windows and logs in `.local/`. It assumes this workspace's `.env` or creates one from `.env.windows.example`; the Windows example uses the local cluster ports, whereas `.env.example` uses standard Docker/service ports. Start only one copy of the launcher. Stop it with `powershell -ExecutionPolicy Bypass -File scripts/stop-local.ps1`; this preserves data and artifacts. Do not replace a personal database configuration with a demo URL.

For a fresh machine, the supported portable setup is **Python 3.12 + uv, Node 22, Docker with Compose**:

```bash
uv sync --frozen --group ml
uv run python -m ml.download
uv run python -m ml.prepare
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 uv run python -m ml.train_baseline
# Optional to rerun the completed transformer comparison, not needed to serve:
uv run python -m ml.train_transformer
# Recompute comparable reports from frozen checkpoints, if both were trained:
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 uv run python -m ml.evaluate_saved
uv run python -m scripts.select_model

docker compose up --build -d
```

The frozen checkpoints exist locally in this delivered workspace. They are ignored by Git; a fresh checkout must run training before building the image. The baseline is ~0.52 MB and trains quickly; the ~18 MB transformer is an offline experiment. The serving image installs runtime dependencies only and **does not download/train models**. The image builds the UI using `npm ci`; it uses the baseline directory explicitly. Stop containers with `docker compose down` to keep data volumes.

**Docker was unavailable here.** Compose YAML was parsed, but image builds, Linux fork workers and Compose startup were not executed. Native PostgreSQL, Redis, worker, dispatcher, API and Chromium were executed successfully. See [deployment preparation](docs/DEPLOYMENT.md) before using another host.

## Native Windows setup / reproduction

The implementation used workspace Python 3.12.16 installed with uv; Python 3.14 was unsuitable for the selected compatibility target. Install uv and run `uv sync --frozen --python 3.12 --group ml`. Use `uv run python` in place of the explicit interpreter below on a new checkout.

```powershell
Copy-Item .env.windows.example .env
# Download the pinned, licensed Bitext CSV; prepare deterministic split groups.
.venv\Scripts\python -m ml.download
$env:OMP_NUM_THREADS='2'; $env:OPENBLAS_NUM_THREADS='2'
.venv\Scripts\python -m ml.prepare
.venv\Scripts\python -m ml.train_baseline
# Network is needed once for the pinned pretrained checkpoint:
$env:HF_HUB_DISABLE_XET='1'
.venv\Scripts\python -m ml.train_transformer
.venv\Scripts\python -m ml.evaluate_saved
.venv\Scripts\python -m scripts.select_model

Set-Location frontend
npm ci
npm run build
Set-Location ..
# Requires installed PostgreSQL 18 at C:\Program Files\PostgreSQL\18\bin.
powershell -ExecutionPolicy Bypass -File scripts/start-local.ps1
```

A native Redis 5.0.14.1 compatibility executable was downloaded from https://github.com/tporadowski/redis/releases/tag/v5.0.14.1 into `.local/redis`; this is an unofficial Windows port used for local verification only. For a fresh Windows native setup, download `Redis-x64-5.0.14.1.zip` from that release and extract it there. Prefer the Redis 7 container for portable deployment. The local PostgreSQL helper initializes only `.local/postgres`, uses trust authentication on loopback for this demo, and never changes the existing Windows PostgreSQL service. Stop the demo cluster with `& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D .local/postgres stop`. Do not expose these local services to a network.

To run services in separate terminals for debugging, first run the PostgreSQL helper, Redis and migrations, then:

```powershell
.venv\Scripts\python scripts/local_postgres.py
.local\redis\redis-server.exe --port 56379 --bind 127.0.0.1 --dir .local/redis --appendonly yes
.venv\Scripts\python -m alembic upgrade head
# Each of the following stays running in a separate terminal:
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
.venv\Scripts\python -m app.jobs
.venv\Scripts\python -m app.worker
```

For UI development, run `npm run dev` in `frontend`; Vite proxies `/api` to port 8000. Rebuild before using the API-served production dashboard.

## Measured results

Both models were actually trained on the same immutable Bitext data and group-disjoint split: **12,883 training / 4,409 validation / 6,327 test samples**, across **11 categories**. The original source has 26,872 rows; 23,619 remain after conflict removal and normalized deduplication. See [dataset attribution, licensing and label meanings](docs/DATASET.md). The source README's category count differs from the pinned CSV; actual CSV labels govern this project.

| Frozen model | Test macro-F1 | Test accuracy | Test auto coverage | Accuracy of auto decisions | Warm median / p95 CPU inference |
| --- | ---: | ---: | ---: | ---: | ---: |
| TF-IDF + logistic regression | 99.50% | 99.53% | 98.55% | 99.82% | 0.60 / 0.75 ms |
| Fine-tuned two-layer BERT | 99.28% | 99.49% | 100.00% | 99.49% | 4.29 / 5.73 ms |

The baseline is deployed. Selection policy: among models reaching **99% validation macro-F1**, choose lower measured median batch-one CPU latency, considering artifact size and process memory. Validation macro-F1 was 99.68% for baseline and 99.92% for BERT. This is a practical latency/resource tradeoff, not a claim that one model universally wins. Test results are final reporting, not the model-selection criterion. Model SHA versions, source commit/hash, commands, hardware, package versions, training times and sizes are in `artifacts/`.

Confidence policy maximizes validation coverage while accepted predictions have at least 98% observed validation accuracy and at least 100 accepted samples, with a confidence floor of 0.50. Both final thresholds are 0.50. The floor was added after the first test report to support human review of ambiguous requests; the audit trail is explicit in each report and no cutoff was optimized against test errors. The baseline's ten-bin test ECE is **0.0763**, versus **0.00081** for BERT. Probabilities are uncalibrated; ECE is diagnostic and in-domain only. The 98% target is empirical, not a statistical guarantee. Some validation classes are very small (INVOICE has eight rows) because related groups are kept intact.

Full precision/recall/F1 per class, confusion matrices, representative errors, confidence bins, Brier scores and threshold coverage/error curves are saved in `artifacts/{baseline,transformer}/evaluation.json`. The dashboard reads these files directly. They are **real evaluations**, separate from the clearly marked fake predictor used in CI tests. Further discussion is in [RESULTS.md](docs/RESULTS.md).

## Queue benchmark

One preloaded persistent Windows worker, 40 requests, concurrency four, eight synthetic texts, 50 ms client polling, one-second dispatcher scan, no concurrent training:

| Measurement | Median | p95 |
| --- | ---: | ---: |
| HTTP submission to observed persisted result | 1,028.98 ms | 1,070.75 ms |
| Creation to worker claim (queue wait) | 930.50 ms | 973.77 ms |
| In-worker model inference | 2.93 ms | 3.31 ms |

**4.15 tickets/second**, 9.63 seconds total, **zero failed tickets**. This small closed-loop experiment is dominated by dispatcher polling. It is not a saturation test or a production capacity claim. Its in-worker timings differ from the warm standalone microbenchmark because of runtime conditions and request texts. Reproduce with `python -m scripts.benchmark --count 40 --concurrency 4`; raw measurements and environment are in `artifacts/benchmark.json`.

## Verification

**19 deterministic unit/PostgreSQL/Redis integration tests + one real Chromium browser test passed.** The browser submitted a request, observed asynchronous inference, saved a manual-review decision, viewed saved evaluation results, and checked mobile overflow. Screenshots are generated locally in `test-results/`.

```powershell
# Uses router_test and Redis database 15, separate from demo data.
.venv\Scripts\python scripts/test_local.py
# With the full application running:
$env:BROWSER_BASE_URL='http://127.0.0.1:8000'
.venv\Scripts\python -m pytest tests/test_browser.py -q
```

Generic CI/local commands:

```bash
uv sync --frozen
export TEST_DATABASE_URL=postgresql+psycopg://router:router@localhost:5432/router_test
export DATABASE_URL="$TEST_DATABASE_URL"
export REDIS_URL=redis://localhost:6379/15
uv run alembic upgrade head
uv run pytest -m 'not browser'
cd frontend && npm ci && npm run build
```

CI provisions real Postgres and Redis but does not download models or retrain. Tests cover concurrent idempotency races, routing, low-confidence review, preserved predictions, bounded exponential retry, scheduling delays, duplicate delivery, queue outages, expired lease redelivery, stale-result fencing, validation and a hard process deadline. Redis integration runs real RQ delivery with a deterministic fake predictor. The browser test requires the separately trained real model and full stack. `uv run playwright install chromium` installs the browser if needed. A native runtime test is not a substitute for running CI on GitHub; that workflow has been prepared but not pushed/executed remotely.

## Design and limits

See [architecture and recovery semantics](docs/ARCHITECTURE.md) for the row-backed outbox, leases, fencing and worker lifecycle. API docs are at `/docs`. Routes are configured in `config/routing.json`; they are invented teams, distinct from dataset labels. Training/source settings are recorded in `config/training.json`, split row/group manifests in `artifacts/split-manifest.json`, and model-choice evidence in `artifacts/model-selection.json`. Baseline TF-IDF and classifier hyperparameters and transformer checkpoints are selected using validation only. Five seeded group folds preserve close textual families, though distant semantic paraphrases may still cross splits because source seed-family IDs are unavailable. Exact normalization and cosine-near duplicates cannot cross splits under the implemented representation.

This is a local, unauthenticated portfolio demo. It has no real users, external deployment, paid infrastructure, or production accuracy claims. English synthetic intent performance does not establish performance on real-world tickets; ambiguous inputs can still be confidently wrong. No language/OOD detector, authentication, per-user access control, fairness study or statistical confidence bounds are provided. Reviews require future manual curation before training use. Feedback and request text have no automatic expiry; implement retention before using private data. Checkpoints use the pinned upstream licenses; application source is provided as portfolio code without an additional project-wide license grant.

Three measured résumé bullets are in [docs/RESUME.md](docs/RESUME.md).
