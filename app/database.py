import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)

# Configure Async Engine
engine_kwargs = {"echo": settings.DEBUG}
db_url = settings.effective_database_url
if db_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_async_engine(db_url, **engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy ORM models."""
    pass

_db_initialized: bool = False
_db_init_hook = None

def register_db_init_hook(hook) -> None:
    """Register an async initialization callback for lazy serverless cold starts."""
    global _db_init_hook
    _db_init_hook = hook

async def ensure_db_initialized() -> None:
    """Ensure database schema and initial owner exist (idempotent per worker)."""
    global _db_initialized
    if _db_initialized or _db_init_hook is None:
        return
    _db_initialized = True
    try:
        await _db_init_hook()
    except Exception as e:
        logger.warning(f"Lazy database initialization warning: {e}")

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session."""
    await ensure_db_initialized()
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
