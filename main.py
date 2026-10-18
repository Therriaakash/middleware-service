
import os
import time
import uuid
import asyncio
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

EMAIL = "22f3002796@ds.study.iitm.ac.in"
WINDOW_SECONDS = 10
MAX_REQUESTS = 15

app = FastAPI()

# Middleware 1: propagate the request ID
class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# Middleware 2: per-client sliding-window rate limiter
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.requests = defaultdict(deque)
        self.lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/ping" and request.method == "GET":
            client_id = request.headers.get("X-Client-Id")
            if not client_id:
                client_id = (
                    request.client.host if request.client else "unknown"
                )

            now = time.monotonic()

            async with self.lock:
                bucket = self.requests[client_id]

                while bucket and now - bucket[0] >= WINDOW_SECONDS:
                    bucket.popleft()

                if len(bucket) >= MAX_REQUESTS:
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Rate limit exceeded"},
                    )

                bucket.append(now)

        return await call_next(request)


# Register inner middleware first; the last registered is outermost.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestContextMiddleware)

# Middleware 3: scoped CORS policy
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://app-y7942k.example.com",
        "https://exam.sanand.workers.dev",
    ],
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["X-Request-ID", "X-Client-Id", "Content-Type"],
)


@app.get("/ping")
async def ping(request: Request):
    return {
        "email": EMAIL,
        "request_id": request.state.request_id,
    }

