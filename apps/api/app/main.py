import time
import uuid
from contextlib import suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import get_settings
from .db import SessionLocal, engine
from .errors import DomainError
from .models import User
from .routers import audit_logs, auth, experiments, organization_users, organizations, projects, suggestions, tasks
from .security import decode_token_claims
from .services.audit_service import add_management_audit

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    docs_url=f"{settings.api_prefix}/docs",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))[:64]
    request.state.correlation_id = correlation_id
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["X-Response-Time-Ms"] = str(round((time.perf_counter() - started) * 1000))
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "type": "about:blank",
            "title": "Internal Server Error",
            "status": 500,
            "detail": "An unexpected error occurred",
            "correlation_id": request.state.correlation_id,
        },
    )


@app.exception_handler(DomainError)
async def domain_exception(request: Request, exc: DomainError) -> JSONResponse:
    if exc.status_code == 403 and request.url.path.startswith(f"{settings.api_prefix}/organizations/"):
        with suppress(Exception):
            organization_id = request.url.path.split("/organizations/", 1)[1].split("/", 1)[0]
            raw_token = request.headers.get("Authorization", "").removeprefix("Bearer ") or request.cookies.get(
                "access_token", ""
            )
            actor_id = str(decode_token_claims(raw_token, "access")["sub"])
            async with SessionLocal() as db:
                actor = await db.get(User, actor_id)
                if actor:
                    add_management_audit(
                        db,
                        request,
                        organization_id,
                        actor,
                        "user.admin.access_denied",
                        None,
                        new_values={"path": request.url.path, "error_code": exc.code},
                        result="denied",
                    )
                    await db.commit()
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "correlation_id": request.state.correlation_id,
            }
        },
    )


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def ready() -> dict[str, str]:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ready"}


for router in (
    auth.router,
    organizations.router,
    projects.router,
    tasks.router,
    suggestions.router,
    experiments.router,
    audit_logs.router,
    organization_users.router,
):
    app.include_router(router, prefix=settings.api_prefix)
