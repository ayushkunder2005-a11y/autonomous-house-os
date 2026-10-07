import asyncio
import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid4()))[:128]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int) -> None:
        super().__init__(app)
        self.limit = requests_per_minute
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in {"/health", "/ready"} or request.url.path.startswith("/api/v1/ws"):
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        async with self._lock:
            history = self._requests[client]
            while history and now - history[0] >= 60:
                history.popleft()
            if len(history) >= self.limit:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "http_429",
                            "message": "Rate limit exceeded",
                            "context": {},
                        },
                        "request_id": getattr(request.state, "request_id", "unknown"),
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )
            history.append(now)
        return await call_next(request)
