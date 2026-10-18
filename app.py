
import os
import time
import json
import logging
import threading
import uuid
from collections import deque
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Query
from fastapi.responses import Response, JSONResponse
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

app = FastAPI()

USER_EMAIL = os.environ.get(
    "USER_EMAIL", "22f2000417@ds.study.iitm.ac.in"
)
START_TIME = time.monotonic()

REQUESTS = Counter(
    "http_requests",
    "Total HTTP requests received by the service",
    ["method", "path", "status"]
)

LOG_LIMIT = 1000
logs = deque(maxlen=LOG_LIMIT)
log_lock = threading.Lock()


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    path = request.url.path
    method = request.method

    try:
        response = await call_next(request)
    except Exception:
        REQUESTS.labels(method, path, "500").inc()
        entry = {
            "level": "ERROR",
            "ts": datetime.now(timezone.utc).isoformat(),
            "path": path,
            "request_id": request_id,
            "method": method,
            "status": 500
        }
        with log_lock:
            logs.append(entry)
        logging.error(json.dumps(entry))
        raise

    REQUESTS.labels(method, path, str(response.status_code)).inc()

    entry = {
        "level": "INFO" if response.status_code < 400 else "ERROR",
        "ts": datetime.now(timezone.utc).isoformat(),
        "path": path,
        "request_id": request_id,
        "method": method,
        "status": response.status_code
    }

    with log_lock:
        logs.append(entry)

    logging.info(json.dumps(entry))
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/work")
async def work(n: int = Query(default=1, ge=0)):
    # Simulate K units of work without adding unnecessary delay.
    return {"email": USER_EMAIL, "done": n}


@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "uptime_s": max(0.0, time.monotonic() - START_TIME)
    }


@app.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


@app.get("/logs/tail")
async def logs_tail(limit: int = Query(default=100, ge=0)):
    with log_lock:
        entries = list(logs)
    return JSONResponse(content=entries[-limit:] if limit else [])
