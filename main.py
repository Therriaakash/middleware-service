
import json
import logging
import os
import time
import uuid
from collections import deque
from datetime import datetime, timezone

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import Counter, CONTENT_TYPE_LATEST, generate_latest

EMAIL = "22f3002796@ds.study.iitm.ac.in"
START_TIME = time.monotonic()

app = FastAPI(title="Instrumented Work Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

REQUESTS = Counter(
    "http_requests",
    "Total number of HTTP requests received",
    ["method", "path", "status"],
)

LOG_ENTRIES = deque(maxlen=2000)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("request_logger")


@app.middleware("http")
async def instrument_requests(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    path = request.url.path
    method = request.method
    started = time.monotonic()
    status = 500

    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception:
        logger.exception("Request failed")
        raise
    finally:
        duration_ms = round((time.monotonic() - started) * 1000, 2)
        REQUESTS.labels(method=method, path=path, status=str(status)).inc()

        entry = {
            "level": "INFO" if status < 500 else "ERROR",
            "ts": datetime.now(timezone.utc).isoformat(),
            "path": path,
            "request_id": request_id,
            "method": method,
            "status": status,
            "duration_ms": duration_ms,
        }
        LOG_ENTRIES.append(entry)
        logger.info(json.dumps(entry))


@app.get("/work")
async def work(n: int = Query(default=1, ge=0, le=100000)):
    # Perform n units of lightweight work.
    checksum = sum(range(n))
    return {"email": EMAIL, "done": n}


@app.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "uptime_s": float(max(0.0, time.monotonic() - START_TIME)),
    }


@app.get("/logs/tail")
async def logs_tail(limit: int = Query(default=100, ge=1, le=2000)):
    return list(LOG_ENTRIES)[-limit:]
