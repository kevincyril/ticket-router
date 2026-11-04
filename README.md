# Relay: support-ticket classification and human review

A local portfolio service with FastAPI, Pydantic, SQLAlchemy/PostgreSQL, Redis/RQ workers, reproducible scikit-learn and PyTorch/Hugging Face training, and a React/TypeScript dashboard.

**Current mode is review-first: automatic routing is disabled.** Broader manual tests exposed confident classification errors hidden by the easy synthetic source benchmark. The improved word/character classifier and validation-selected abstention policy reduce experimental unsafe routes but remain unreliable. All new tickets receive model suggestions and require a human routing decision. Existing ticket results remain unchanged.

## Open the app

Dependencies, models and dashboard are already installed and built in this workspace. Services are left running for review at **http://127.0.0.1:8000**. Interactive API docs: **http://127.0.0.1:8000/docs**.

If stopped, launch from this workspace:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-local.ps1
```

Stop the owned processes with `powershell -ExecutionPolicy Bypass -File scripts/stop-local.ps1`; data and artifacts are retained. Start one launcher instance only. Logs are in `.local/`. The native setup uses isolated PostgreSQL18 on port55432 and local Redis on56379, without changing the pre-existing PostgreSQL service. `.env.windows.example` has those ports; `.env.example` uses standard service ports.

Use synthetic examples. No authentication or private-customer-data protections are implemented. Do not expose the local demo publicly.

## What works

Submit a ticket, follow its queue/inference status, inspect predicted category, raw/scaled class score and review reasons, then choose a category to assign its configured team. Review decisions are stored separately and never retrain the model. The evaluation view shows both historical source-dataset metrics and the new held-out behavioral comparison.

The worker uses idempotency keys, bounded retry/backoff, database leases, fencing tokens and durable dispatch state for restart/outage recovery. Migration002 adds nullable `routing_evidence` without rewriting historical predictions. Class confidence is conditional on a supported single-intent request; it is not the probability that an automated decision would be safe. Model and policy versions remain persisted per ticket.

## Honest before/after results

Frozen author-created challenge test: **88 cases**, comprising48 varied single-intent paraphrases,12 vague requests,12 mixed-intent requests and16 unrelated requests. Separate65-case validation data selected the model/policy. The three user-reported examples are development cases, excluded from classifier training and both challenge sets.

| Model/policy | Unsafe auto routes /88 | Automatic coverage | Accuracy of auto routes | Manual review |
|---|---:|---:|---:|---:|
| Original baseline, threshold0.50 |18|37.5%|45.5%|62.5%|
| Trained original transformer, threshold0.50 |51|87.5%|33.8%|12.5%|
| Improved word/character candidate + validation gates |7|19.3%|58.8%|80.7%|
| **Deployed review-first mode** |**0**|**0%**|**Undefined: no automatic decisions**|**100%**|

Unsafe means a wrong category on a clear request, or any automatic routing of an input labeled must-review. The richer classifier improves clear-request top-1 accuracy from45.8% to54.2%; the frozen transformer achieves60.4%. The candidate was selected on validation before opening test; it was not replaced or retuned after test. Its held-out result vetoed automatic deployment. This is not a successful solution to general automatic classification.

The original 99.50% baseline source-test macro-F1 describes templated, in-domain synthetic data. It does not establish real-ticket performance. Historical metrics remain available, explicitly labeled as such. Scalar calibration improved easy in-domain baseline scores but worsened calibration under shifted wording; higher class scores did not mean safer decisions.

See [the full investigation](docs/ROBUSTNESS.md) for training evidence, class imbalance, TF-IDF contributions, calibration, per-failure-type comparisons, exact protocol, remaining errors and development-case outcomes. Raw predictions and model-selection evidence are in `artifacts/robustness/`; frozen cases and hashes are in `data/challenge/`. This small set was authored by the implementing assistant, not independently annotated or sampled from real traffic.

**Refund is supported:** dataset category `REFUND` contains refund request, policy and status intents, and maps to the invented team **Returns**. `PAYMENT` covers payment issues/methods and maps to Billing. A duplicate charge followed by a request for reimbursement spans both. Returns is a team name, not a separate dataset category. [Dataset license, attribution and taxonomy](docs/DATASET.md).

## Reproduce training and evaluation

Requires Python3.12, uv, Node22, PostgreSQL and Redis (or Docker Compose). Runtime and test dependencies are pinned in `uv.lock`; frontend dependencies in `frontend/package-lock.json`.

```powershell
uv sync --frozen --python 3.12 --group ml
# Pinned public Bitext data; CDLA-Sharing-1.0 license and source retained locally.
uv run --group ml python -m ml.download
uv run --group ml python -m ml.prepare
$env:OMP_NUM_THREADS='2'; $env:OPENBLAS_NUM_THREADS='2'
uv run --group ml python -m ml.train_baseline
# Downloads the pinned small pretrained Google BERT once, then actually fine-tunes.
$env:HF_HUB_DISABLE_XET='1'
uv run --group ml python -m ml.train_transformer
# Existing frozen challenge files must be kept unchanged.
uv run --group ml python -m ml.robustness_select
uv run --group ml python -m scripts.package_robust_model
uv run --group ml python -m ml.robustness_evaluate
```

Only original source training rows fit classifier features/weights. Calibration and routing/model selection use validation data only. `robustness_select` never scores challenge test. `robustness_evaluate` checks hashes, scores frozen policies and does not optimize cutoffs. Rerunning an exposed test is reproduction, not a new untouched evaluation. `scripts/freeze_challenge.py` documents authorship and refuses to overwrite frozen files; do not regenerate/edit them for tuning.

The current serving bundle is `artifacts/robustness/deployed`. `.env` and Compose set `MODEL_DIR` to it and `AUTO_ROUTING_ENABLED=false`. Keep automatic routing disabled: the experimental threshold0.65 plus support/agreement/clause gates has not demonstrated reliable broad routing. The flag is a deployment veto, not a test-tuned probability threshold. No generated sentence, keyword override or feedback retraining is used.

The data preparation/training settings, versions, split manifests, environment, hardware and commands are saved alongside reports. Binary model/support artifacts are present locally but Git-ignored; a fresh checkout must train/package them before serving. The transformer stays an offline comparison; the serving runtime does not need PyTorch.

## Free hosted demo

`render.yaml` defines a free-only Render preview: one Docker web instance supervising API/dispatcher/worker, plus free Redis-compatible Key Value and an external Neon Free PostgreSQL database. Hosting requires connecting Render and granting access to this private repository; a prepared configuration is not a live deployment. The public sandbox accepts only supplied synthetic examples, disables free-text review notes and caps storage at500 tickets. Mandatory review remains enabled. See [the concrete deployment setup](docs/DEPLOYMENT.md), including idle sleep and free usage quotas. Neon avoids the earlier30-day Render database expiry; recruiters can use the public link without signing in.

The committed ~2.3MB bundle in `deploy/` contains only the already-trained serving model/support artifacts and a checksum manifest. It is extracted and verified during image build; no training or large checkpoint download happens in deployment.

## Build and launch elsewhere

Build the UI:

```powershell
Set-Location frontend
npm ci
npm run build
Set-Location ..
```

For native Windows, copy `.env.windows.example` to `.env` and use `scripts/start-local.ps1`. It expects PostgreSQL18 binaries in `C:\Program Files\PostgreSQL\18\bin` and the local Redis executable at `.local/redis/redis-server.exe`. The installed local Redis5.0.14.1 is an unofficial compatibility port from https://github.com/tporadowski/redis/releases/tag/v5.0.14.1. Prefer Redis7 through Compose on a fresh host.

After training/packaging on a Docker-capable machine:

```bash
docker compose config
docker compose up --build -d
```

Compose targets PostgreSQL17 and Redis7. **Docker is unavailable on the local Windows host.** GitHub Actions now builds the image and verifies real queued inference with a Linux RQ worker under a512MB memory limit. Compose startup itself remains unverified. Native PostgreSQL/Redis, API, dispatcher, worker, migrations and browser flow have run successfully. No resources were provisioned and nothing was published. See [deployment notes](docs/DEPLOYMENT.md) and [architecture](docs/ARCHITECTURE.md), with historical sections identified.

## Tests

The updated suite passes **39 backend/unit/reliability checks plus two Chromium flows**. It includes confidence-without-support rejection, calibration limitations, clause conflict, offline/serving policy agreement, frozen evaluation integrity, migration startup, manual-mode override of high confidence, real-model development-case review, idempotency races, retries, fencing, queue outages and restart recovery. Development-case regressions are not independent evaluation. Browser checks include review explanations, the robustness table, saved human decisions and mobile overflow.

```powershell
# Resets only the dedicated router_test fixture tables, migrates, uses Redis DB15.
.venv\Scripts\python scripts/test_local.py
# With the full service running:
$env:BROWSER_BASE_URL='http://127.0.0.1:8000'
.venv\Scripts\python -m pytest tests/test_browser.py -q
```

CI runs `uv sync --frozen`, migrations, the deterministic test suite and TypeScript/Vite build with real PostgreSQL/Redis services, then builds and smoke-tests the hosted Docker image with the packaged model under a512MB limit. Locally trained-artifact tests skip if the artifacts are absent; CI never downloads large checkpoints or retrains. The existing source benchmark and40-ticket queue benchmark are historical in `docs/RESULTS.md`. Current candidate inference/evidence checking measured2.48ms median /6.47ms p95 on88 inputs, excluding HTTP/queue/database time.

Remaining work before restoring useful automatic routing is representative labeled data, explicit ambiguity/scope handling, independent annotation and a new untouched test. The current model still misclassifies some clear requests and can be confidently wrong; human review is a safety mechanism, not proof the classifier is fixed.
