# Free Render demo deployment

The repository contains `render.yaml` and an immutable trained-model bundle for a **temporary, free-only synthetic demo**. No paid worker, disk, database plan, or upgraded compute is requested. Hosting has not been created until the Render account is connected and the Blueprint is applied.

## Concrete deployment

- Web: `relay-ticket-demo`, Docker, `plan: free`, Oregon. Runs `python -m app.hosted` on Render's supplied PORT.
- Database: `relay-ticket-db`, managed PostgreSQL, `plan: free`, same region. No external database access.
- Queue: `relay-ticket-queue`, Redis-compatible Key Value, `plan: free`, same region. No external queue access; eviction disabled.
- One web instance supervises the API, dispatcher, and real Linux RQ worker. Dedicated background workers are not part of this free plan. Any child exit recycles the instance. Migrations run at startup before workers/API.
- `AUTO_ROUTING_ENABLED=false`, `DEMO_MODE=true`, 500-ticket maximum, single-thread numerical libraries. All submissions use supplied synthetic examples. Review notes are disabled and reviewer is fixed to Demo visitor. This is an intentionally shared public sandbox; local mode still supports custom ticket text.

The trained word/character classifier and its support matrix are packaged as `deploy/serving-model.tar.gz` (~2.3MB). Exact file SHA-256 values and model version are recorded beside it. The image verifies and unpacks that trusted bundle; it never trains or downloads model checkpoints. The Bitext attribution and unmodified data license are included in the image. The private source repository can therefore build an identical serving bundle without relying on ignored local files.

## Launch

Connect Render to this session, choose the intended workspace, and grant Render access to the private `kevincyril/ticket-router` GitHub repository. Apply `render.yaml` as a Blueprint. Check **every service remains Free**, no existing unrelated resource is being updated, and no payment method or plan upgrade is requested. Stop rather than accepting a paid substitution if a free instance quota is unavailable.

The Blueprint uses generated internal datastore connection strings; no credentials are committed. Auto-deployment is off, so pushes do not trigger repeated hosting builds. There is no automatic paid upgrade. If the account already has billing configured, inspect its usage/spend settings because Render documents separate bandwidth/build usage allowances. This task does not authorize paid usage or billing changes.

After Render reports a live deployment, verify its returned URL, `/api/health/ready` and `/api/model`, then run:

```bash
uv run python scripts/smoke_hosted.py --base https://ACTUAL-RETURNED-SERVICE.onrender.com
```

The smoke check uses the real queue, Linux worker and PostgreSQL, verifies model version and mandatory review, saves a human routing decision, rejects arbitrary visitor text and checks that private review notes are rejected. It does not measure classification accuracy. Verify the dashboard in a browser afterward. Do not report a guessed service URL as deployed.

## Free-tier limitations

Render's free web service sleeps after15 minutes without inbound traffic and normally takes about a minute to wake. The free PostgreSQL database expires30 days after creation and does not have managed backups. Free Key Value is in-memory and loses queued data on restart; the database-backed dispatcher can redeliver unfinished tickets after leases expire. Free resources can restart and have usage limits. These constraints make this a portfolio preview, not durable production hosting.

The ticket cap bounds application storage. At the cap, existing results/evaluation remain visible but new unique submissions return429. Idempotent replay still works. There is no automatic deletion of user or local database contents. A new demo cycle requires an explicit operator decision. Do not put real customer information here.

Official references: [free services and limits](https://render.com/docs/free), [Blueprint fields](https://render.com/docs/blueprint-spec).

## Verification and updates

The GitHub workflow runs unit/PostgreSQL/Redis tests, builds this Docker image, and starts it with a512MB memory limit against real services. It then runs the hosted smoke check with the actual packaged model and Linux process worker. Docker is unavailable on the local Windows host, so container verification runs on GitHub's Linux runner. Deployment status is separate from a passing container test.

To update the trained bundle after an intentional offline model release:

```bash
uv run python scripts/model_bundle.py pack
```

Review the manifest/version, commit the trusted bundle, pass CI, then explicitly deploy on Render. Preserve review-first mode until a new representative validation/test study justifies automatic routing. No feedback-driven retraining occurs.

For local development, `scripts/start-local.ps1` remains available. Compose still runs the separate API/worker/dispatcher processes and datastores; its container image now obtains model files from the committed verified bundle.

## Prepared-image verification

GitHub Actions run https://github.com/kevincyril/ticket-router/actions/runs/41769007112 passed: dependency lock, migrations, backend tests, TypeScript/Vite build, Docker build,512MB runtime and actual Linux-worker queued inference/review. Local backend verification passes39 tests. A separate Chromium flow checks the synthetic-only public interface and disabled review-note controls. These checks verify the deployment artifact; no Render deployment or live hosted URL is claimed before account authorization.
