"""Postgres owns retry/lease state. RQ is an at-least-once delivery transport."""
import json
import logging
import time
import uuid
from datetime import timedelta
from redis import Redis
from rq import Queue
from sqlalchemy import select, update, or_
from app.config import settings
from app.db import Session, Ticket, utcnow
from app.predictor import predictor, routing

log = logging.getLogger("router.jobs")


def queue():
    return Queue("tickets", connection=Redis.from_url(settings().redis_url, socket_connect_timeout=2, socket_timeout=5), default_timeout=settings().job_timeout)


def process_ticket(ticket_id, expected_attempt=None):
    token = str(uuid.uuid4())
    now = utcnow()
    with Session.begin() as db:
        ticket = db.scalar(select(Ticket).where(Ticket.id == ticket_id).with_for_update())
        if ticket is None or ticket.status not in ("queued", "processing"):
            return
        if ticket.status == "processing" and ticket.lease_until and ticket.lease_until > now:
            return
        if expected_attempt is not None and ticket.attempts != expected_attempt:
            return
        if ticket.attempts >= settings().max_attempts:
            ticket.status, ticket.last_error = "failed", "attempts_exhausted"
            return
        ticket.status = "processing"
        ticket.attempts += 1
        ticket.lease_token = token
        ticket.lease_until = now + timedelta(seconds=settings().lease_seconds)
        ticket.updated_at = now
        ticket.queue_wait_ms = (now - ticket.created_at).total_seconds() * 1000
        text = ticket.text
    try:
        model = predictor()
        if hasattr(model,"assess"):
            result=model.assess(text)
            category,confidence,latency=result['category'],result['confidence'],result['inference_ms']
            auto_route=result['auto_route']
            routing_evidence=result['evidence']
        else:
            category,confidence,latency=model.predict(text)
            auto_route=confidence>=model.metadata['threshold']
            routing_evidence=None
        if not settings().auto_routing_enabled:
            routing_evidence=dict(routing_evidence or {})
            routing_evidence['candidate_auto_route']=auto_route
            routing_evidence['review_reasons']=list(routing_evidence.get('review_reasons',[]))+['automatic_routing_disabled']
            auto_route=False
        rules = routing()
        threshold = model.metadata["threshold"]
        team = rules.get(category)
        with Session.begin() as db:
            # Fencing token prevents a timed-out original job overwriting recovery.
            ticket = db.scalar(select(Ticket).where(Ticket.id == ticket_id).with_for_update())
            if ticket.lease_token != token or ticket.status != "processing":
                return
            ticket.status = "routed" if auto_route and team else "review"
            ticket.predicted_category, ticket.confidence = category, confidence
            ticket.assigned_team = team if ticket.status == "routed" else None
            ticket.model_version = model.metadata["version"]
            ticket.threshold, ticket.routing_snapshot = threshold, rules
            ticket.routing_evidence = routing_evidence
            ticket.inference_ms = latency
            ticket.updated_at = ticket.completed_at = utcnow()
            ticket.lease_until = None
            ticket.last_error = None
        log.info(json.dumps({"event": "inference_complete", "ticket_id": ticket_id, "inference_ms": latency}))
    except Exception as exc:
        with Session.begin() as db:
            ticket = db.scalar(select(Ticket).where(Ticket.id == ticket_id).with_for_update())
            if ticket.lease_token == token and ticket.status == "processing":
                ticket.last_error = type(exc).__name__  # Never log private ticket text.
                ticket.status = "failed" if ticket.attempts >= settings().max_attempts else "queued"
                ticket.dispatch_after = utcnow() + timedelta(seconds=settings().retry_base_seconds * 2 ** (ticket.attempts - 1))
                ticket.lease_until = None
                ticket.updated_at = utcnow()
        log.error(json.dumps({"event": "inference_failed", "ticket_id": ticket_id, "error": type(exc).__name__}))
        raise


def dispatch_once():
    """Commit durable tickets first; redis failures never lose submissions.

    Re-deliver after dispatch lease expiry even if the enqueue acknowledgement
    was lost. Worker claims plus fencing make duplicate delivery safe.
    """
    now = utcnow()
    count = 0
    with Session.begin() as db:
        tickets = db.scalars(select(Ticket).where(or_(
            (Ticket.status == "queued") & (Ticket.dispatch_after <= now),
            (Ticket.status == "processing") & (Ticket.lease_until <= now),
        )).order_by(Ticket.created_at).limit(100).with_for_update(skip_locked=True)).all()
        for ticket in tickets:
            if ticket.attempts >= settings().max_attempts:
                ticket.status, ticket.last_error = "failed", "attempts_exhausted"
                continue
            queue().enqueue("app.jobs.process_ticket", ticket.id, ticket.attempts, job_id=str(uuid.uuid4()),
                            job_timeout=settings().job_timeout, result_ttl=3600, failure_ttl=604800)
            ticket.dispatch_after = now + timedelta(seconds=settings().lease_seconds)
            count += 1
    return count


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if settings().lease_seconds <= settings().job_timeout:
        raise ValueError("LEASE_SECONDS must exceed JOB_TIMEOUT")
    while True:
        try:
            dispatch_once()
        except Exception as exc:
            log.error(json.dumps({"event": "dispatch_failed", "error": type(exc).__name__}))
        time.sleep(1)


if __name__ == "__main__":
    main()
