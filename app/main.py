import hashlib
import logging
import time
import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Literal
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sqlalchemy import select, func, text as sqltext
from sqlalchemy.exc import IntegrityError
from redis import Redis
from app.config import settings
from app.db import Session, Ticket, Review, utcnow
from app.predictor import routing

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("router.api")

app = FastAPI(title="Relay / Support ticket routing", version="0.1.0")


@app.middleware("http")
async def request_log(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    request_id = str(uuid.uuid4())
    response.headers["X-Request-ID"] = request_id
    log.info(json.dumps({"event": "http_request", "request_id": request_id,
                         "method": request.method, "status": response.status_code,
                         "latency_ms": round((time.perf_counter()-start)*1000, 2)}))
    return response


class Submission(BaseModel):
    text: str = Field(min_length=8, max_length=5000)

    @field_validator("text")
    @classmethod
    def nonempty(cls, value):
        value = value.strip()
        if len(value) < 8 or "\x00" in value:
            raise ValueError("Use 8–5000 characters without null bytes")
        return value


class Decision(BaseModel):
    category: str = Field(max_length=64)
    reviewer: str = Field(min_length=1, max_length=80)
    note: str = Field(default="", max_length=1000)


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    text: str
    status: str
    model_version: str | None
    predicted_category: str | None
    confidence: float | None
    assigned_team: str | None
    routing_evidence: dict | None
    threshold: float | None
    attempts: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    queue_wait_ms: float | None
    inference_ms: float | None
    last_error: str | None


def serialize(ticket):
    return TicketOut.model_validate(ticket).model_dump(mode="json")


@app.exception_handler(Exception)
async def unexpected(request, exc):
    import logging
    logging.getLogger("router.api").error(json.dumps({"event": "request_failed", "error": type(exc).__name__}))
    return JSONResponse(status_code=503, content={"detail": "Service temporarily unavailable"})


@app.get("/api/health/live")
def live():
    return {"status": "alive"}


@app.get("/api/health/ready")
def ready():
    try:
        with Session() as db:
            db.execute(sqltext("SELECT 1 FROM tickets LIMIT 1"))
        Redis.from_url(settings().redis_url, socket_connect_timeout=2, socket_timeout=5).ping()
        path = Path(settings().model_dir)
        metadata = json.loads((path / "metadata.json").read_text(encoding='utf-8-sig'))
        if metadata.get("routing_policy") and not (path / "support.joblib").exists():
            raise ValueError("support artifact missing")
        if not (path / "model.joblib").exists() or set(metadata["labels"]) - set(routing()):
            raise ValueError("model or routing incomplete")
    except Exception:
        raise HTTPException(503, "Database, queue, model or routing is not ready")
    return {"status": "ready", "version": metadata["version"]}


@app.post("/api/tickets", status_code=202)
def submit(body: Submission, idempotency_key: str = Header(min_length=1, max_length=128)):
    digest = hashlib.sha256(body.text.encode()).hexdigest()
    with Session() as db:
        previous = db.scalar(select(Ticket).where(Ticket.idempotency_key == idempotency_key))
        if previous:
            if previous.request_hash != digest:
                raise HTTPException(409, "Idempotency key was already used with different text")
            return serialize(previous)
        ticket = Ticket(id=str(uuid.uuid4()), idempotency_key=idempotency_key, request_hash=digest, text=body.text)
        db.add(ticket)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            previous = db.scalar(select(Ticket).where(Ticket.idempotency_key == idempotency_key))
            if previous is None or previous.request_hash != digest:
                raise HTTPException(409, "Idempotency key conflict")
            return serialize(previous)
        return serialize(ticket)


@app.get("/api/tickets")
def tickets(status: Literal["queued", "processing", "routed", "review", "reviewed", "failed"] | None = None,
            limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)):
    with Session() as db:
        query = select(Ticket)
        if status:
            query = query.where(Ticket.status == status)
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        items = db.scalars(query.order_by(Ticket.created_at.desc(), Ticket.id).offset(offset).limit(limit)).all()
        return {"items": [serialize(t) for t in items], "total": total, "offset": offset, "limit": limit}


@app.get("/api/tickets/{ticket_id}")
def ticket(ticket_id: str):
    with Session() as db:
        item = db.get(Ticket, ticket_id)
        if item is None:
            raise HTTPException(404, "Ticket not found")
        review = db.scalar(select(Review).where(Review.ticket_id == ticket_id))
        return {**serialize(item), "review": None if review is None else {
            "category": review.category, "team": review.team, "reviewer": review.reviewer,
            "note": review.note, "created_at": review.created_at.isoformat()}}


@app.post("/api/tickets/{ticket_id}/review")
def review(ticket_id: str, body: Decision):
    rules = routing()
    if body.category not in rules:
        raise HTTPException(422, "Unknown category")
    with Session.begin() as db:
        item = db.scalar(select(Ticket).where(Ticket.id == ticket_id).with_for_update())
        if item is None:
            raise HTTPException(404, "Ticket not found")
        if item.status != "review":
            raise HTTPException(409, "Only tickets awaiting review can be reviewed")
        db.add(Review(id=str(uuid.uuid4()), ticket_id=item.id, category=body.category,
                      team=rules[body.category], reviewer=body.reviewer, note=body.note))
        item.status, item.assigned_team, item.updated_at = "reviewed", rules[body.category], utcnow()
        return serialize(item)


@app.get("/api/model")
def model():
    path = Path(settings().model_dir)
    if not (path / "metadata.json").exists():
        raise HTTPException(503, "Train a model first")
    return {"metadata": json.loads((path / "metadata.json").read_text(encoding='utf-8-sig')), "routing": routing(), "automatic_routing_enabled": settings().auto_routing_enabled}


@app.get("/api/evaluation")
def evaluation():
    results = {}
    for name in ("baseline", "transformer"):
        path = Path("artifacts") / name / "evaluation.json"
        results[name] = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {"status": "not_evaluated"}
    return results


@app.get("/api/robustness")
def robustness():
    path=Path("artifacts/robustness/results.json")
    if not path.exists():
        raise HTTPException(503,"Robustness evaluation not completed")
    report=json.loads(path.read_text(encoding="utf-8"))
    report['results']={name:{key:value for key,value in entry.items() if key!='rows'} for name,entry in report['results'].items()}
    report['deployment']=json.loads(Path("artifacts/robustness/deployment-decision.json").read_text(encoding="utf-8"))
    return report


@app.get("/api/metrics")
def metrics():
    with Session() as db:
        counts = dict(db.execute(select(Ticket.status, func.count()).group_by(Ticket.status)).all())
        summary = db.execute(select(func.avg(Ticket.queue_wait_ms), func.avg(Ticket.inference_ms), func.sum(Ticket.attempts))).one()
        completed = sum(counts.get(s, 0) for s in ("routed", "review", "reviewed"))
        return {"counts": counts, "queue_wait_mean_ms": summary[0], "inference_mean_ms": summary[1],
                "attempts": summary[2] or 0, "failures": counts.get("failed", 0),
                "manual_review_rate": (counts.get("review", 0) + counts.get("reviewed", 0)) / completed if completed else None}


if Path(settings().frontend_dir).exists():
    app.mount("/", StaticFiles(directory=settings().frontend_dir, html=True), name="dashboard")
