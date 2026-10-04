"""Suraksha AI - FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from backend.ai.guardrails import DISCLAIMER
from backend.api.router import api_router
from backend.config import settings
from backend.security.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from backend.security.rate_limit import limiter
from backend.utils.logging import configure_logging, get_logger, request_id_ctx

configure_logging()
log = get_logger("suraksha")

DESCRIPTION = f"""
**Suraksha AI** protects Indian investors from scams, financial misinformation, phishing, fake
investment schemes and risky financial behaviour. All AI runs locally via Ollama - no paid APIs.

> {DISCLAIMER}

Authenticate with `POST /auth/register` or `POST /auth/login`, then click **Authorize** and paste the
`access_token`.
"""

TAGS = [
    {"name": "Authentication", "description": "JWT + Google OAuth login"},
    {"name": "Scam Detection", "description": "Module 1 - OCR + rules + LLM scam analysis for images, PDFs and text"},
    {"name": "Message & Social Analysis", "description": "Modules 2 & 3 - WhatsApp messages and social-media content"},
    {"name": "AI Safety Assistant", "description": "RAG-grounded chat (never gives investment advice)"},
    {"name": "Voice Assistant", "description": "Module 5 - Whisper + Ollama + Coqui TTS"},
    {"name": "Dashboard", "description": "Safety score, history, alerts and progress"},
    {"name": "Learning Center", "description": "Module 6 - lessons, flash cards and assessments"},
    {"name": "Financial Habit Coach", "description": "Module 4 - behavioural nudges, no recommendations"},
    {"name": "Progress & Rewards", "description": "XP, levels, badges, activity heatmap and feed"},
    {"name": "Family Protection", "description": "Trusted contacts, Get Help button and automatic family alerts"},
    {"name": "Admin", "description": "RBAC-protected administration"},
    {"name": "System", "description": "Health and task status"},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if settings.is_production and settings.SECRET_KEY.startswith("change-me"):
        raise RuntimeError("SECRET_KEY must be set to a strong random value in production")
    log.info("%s %s starting (%s)", settings.APP_NAME, settings.APP_VERSION, settings.ENVIRONMENT)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=DESCRIPTION,
    openapi_tags=TAGS,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    swagger_ui_parameters={"persistAuthorization": True},
)

app.state.limiter = limiter

# Order: last added runs first.
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limited(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
        headers={"Retry-After": "60"},
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Do not echo raw input back (avoids reflecting injected markup / secrets).
    errors = [{"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "request_id": request_id_ctx.get()},
    )


app.include_router(api_router, prefix=settings.API_PREFIX)


@app.get("/", include_in_schema=False)
def root():
    return {"name": settings.APP_NAME, "docs": "/docs", "health": "/health", "disclaimer": DISCLAIMER}
