import logging
import os
import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure project root (/var/task on Vercel) is in sys.path when app/main.py is loaded via importlib
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

app = FastAPI(
    title="NORE",
    description="NORE - Production Real-Time Voice Intelligence Platform with ElevenLabs streaming, WebSockets, RBAC, and Monitoring",
    version="1.0.0",
)

try:
    from sqlalchemy import select
    from app.api import api_router
    from app.config import settings
    from app.database import AsyncSessionLocal, Base, engine, ensure_db_initialized, register_db_init_hook
    from app.models.user import RoleEnum, User, UserVoicePreference
    from app.security.passwords import hash_password
    from app.services.elevenlabs import elevenlabs_service
    from app.security.logging import SensitiveDataFilter
    from app.websockets import websocket_router

    # Configure logging with secret sanitization
    logging.basicConfig(
        level=logging.INFO if not settings.DEBUG else logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    root_logger = logging.getLogger()
    root_logger.addFilter(SensitiveDataFilter())

    logger = logging.getLogger("nore")
    logger.addFilter(SensitiveDataFilter())

    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        """Add defensive security headers to all HTTP responses."""
        async def dispatch(self, request: Request, call_next):
            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            if request.url.path.startswith("/static") or request.url.path == "/":
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
            if settings.is_production:
                response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            return response

    async def seed_initial_owner():
        """Ensure Owner account exists, preventing casual recreation or predictable passwords."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.role == RoleEnum.OWNER))
            owner = result.scalars().first()
            if owner:
                logger.info(f"Owner account verified: {owner.email} (Protected Principal)")
                return

            email = (settings.OWNER_INITIAL_EMAIL or "").strip().lower()
            password = (settings.OWNER_INITIAL_PASSWORD or "").strip()

            if email:
                existing_res = await db.execute(select(User).where(User.email == email))
                existing_user = existing_res.scalars().first()
                if existing_user:
                    existing_user.role = RoleEnum.OWNER
                    existing_user.status = "active"
                    existing_user.is_active = True
                    await db.commit()
                    logger.info(f"Existing account elevated to platform Owner: {email}")
                    return

            if email and len(password) >= 12:
                logger.info(f"Initializing platform Owner principal: {email}")
                owner_user = User(
                    email=email,
                    hashed_password=hash_password(password),
                    full_name="Platform Owner",
                    role=RoleEnum.OWNER,
                    status="active",
                    is_active=True,
                    daily_character_quota=5000000,
                    token_version=1,
                )
                db.add(owner_user)
                await db.flush()

                pref = UserVoicePreference(
                    user_id=owner_user.id,
                    preferred_voice_id=settings.ELEVENLABS_DEFAULT_VOICE_ID,
                    preferred_model_id=settings.ELEVENLABS_DEFAULT_MODEL_ID,
                    preferred_voice_name="Roger",
                )
                db.add(pref)
                await db.commit()
                logger.info("Platform Owner principal initialized successfully.")
            else:
                logger.warning(
                    "No Owner account exists. Please run 'python scripts/init_owner.py' to securely initialize the platform Owner."
                )

    async def initialize_database_and_owner():
        """Create database tables and seed initial platform Owner if missing."""
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            if engine.dialect.name == "sqlite":
                from sqlalchemy import text
                for col, col_type, default_val in [
                    ("tech_interests", "VARCHAR(255)", "'ai_ml,software_dev,cybersecurity'"),
                    ("tech_explanation_level", "VARCHAR(50)", "'intermediate'"),
                    ("tech_briefing_topics", "VARCHAR(255)", "'all'"),
                    ("tech_summary_style", "VARCHAR(50)", "'balanced'"),
                ]:
                    try:
                        await conn.execute(
                            text(f"ALTER TABLE user_voice_preferences ADD COLUMN {col} {col_type} DEFAULT {default_val}")
                        )
                    except Exception:
                        pass

        await seed_initial_owner()

    register_db_init_hook(initialize_database_and_owner)

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI):
        """Application lifespan manager handling DB setup and graceful shutdown."""
        logger.info("Initializing NORE platform...")
        await ensure_db_initialized()
        logger.info(f"ElevenLabs Key Loaded: {settings.masked_elevenlabs_key()}")
        yield
        logger.info("Shutting down NORE...")
        try:
            await elevenlabs_service.close()
        except Exception:
            pass
        try:
            await engine.dispose()
        except Exception:
            pass

    app.router.lifespan_context = lifespan

    # Middleware
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_origin_regex=r"^https?://.*\.(trycloudflare\.com|vercel\.app)$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """
        Defensive global exception handler per Master PDR Section 45.
        Never expose internal stack traces, API keys, or database credentials.
        """
        logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}")
        return JSONResponse(
            status_code=500,
            content={"detail": "An internal error occurred. Please contact system administrator."},
        )

    # Include Routers
    app.include_router(api_router)
    app.include_router(websocket_router)

    @app.get("/health", tags=["Health"])
    async def root_health_check():
        """Standard liveness probe per Master PDR Section 46."""
        return {"status": "healthy"}

    @app.get("/api/health", tags=["Health"])
    async def api_health_check():
        """API health check with service metadata."""
        return {"status": "healthy", "service": settings.APP_NAME, "version": "1.0.0"}

    # Mount Static Frontend
    def _resolve_static_dir() -> Path:
        for candidate in (
            Path(__file__).resolve().parent / "static",
            Path.cwd() / "app" / "static",
            Path("/var/task/app/static"),
        ):
            if candidate.exists() and (candidate / "index.html").exists():
                return candidate
        return Path(__file__).resolve().parent / "static"

    STATIC_DIR = _resolve_static_dir()
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.get("/")
        async def serve_index():
            return FileResponse(str(STATIC_DIR / "index.html"))
    else:
        @app.get("/")
        async def serve_index_fallback():
            return {"app": settings.APP_NAME, "status": "running", "docs": "/docs"}

except BaseException as _startup_exc:
    _err_msg = f"{type(_startup_exc).__name__}: {_startup_exc}"

    @app.get("/health")
    @app.get("/{path:path}")
    async def _startup_error_handler(path: str = ""):
        return JSONResponse(
            status_code=503,
            content={
                "status": "startup_error",
                "error": _err_msg,
            },
        )
