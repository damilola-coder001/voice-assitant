import asyncio
import os
from typing import AsyncGenerator
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.user import RoleEnum, User, UserVoicePreference
from app.security.passwords import hash_password
from app.security.rate_limiter import rate_limiter
from app.security.tokens import create_access_token

# Use in-memory SQLite database for test isolation
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Ensure RBAC validation is active during test suite runs to verify underlying policy integrity
settings.ENABLE_RBAC = True

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

app.dependency_overrides[get_db] = override_get_db

@pytest_asyncio.fixture(autouse=True)
async def prepare_database():
    rate_limiter.reset()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    rate_limiter.reset()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session

@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        email="testuser@example.com",
        hashed_password=hash_password("Password123!"),
        full_name="Test User",
        role=RoleEnum.USER,
        is_active=True,
        daily_character_quota=50000,
    )
    db_session.add(user)
    await db_session.flush()

    pref = UserVoicePreference(user_id=user.id)
    db_session.add(pref)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def test_admin(db_session: AsyncSession) -> User:
    admin = User(
        email="admin@example.com",
        hashed_password=hash_password("AdminPassword123!"),
        full_name="Admin User",
        role=RoleEnum.ADMIN,
        is_active=True,
        daily_character_quota=1000000,
    )
    db_session.add(admin)
    await db_session.flush()

    pref = UserVoicePreference(user_id=admin.id)
    db_session.add(pref)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin

@pytest_asyncio.fixture
def user_token(test_user: User) -> str:
    return create_access_token(test_user.id, test_user.email, test_user.role.value, token_version=test_user.token_version)

@pytest_asyncio.fixture
def admin_token(test_admin: User) -> str:
    return create_access_token(test_admin.id, test_admin.email, test_admin.role.value, token_version=test_admin.token_version)

@pytest_asyncio.fixture
async def test_owner(db_session: AsyncSession) -> User:
    owner = User(
        email="owner@example.com",
        hashed_password=hash_password("OwnerPassword123!"),
        full_name="Owner Principal",
        role=RoleEnum.OWNER,
        status="active",
        is_active=True,
        daily_character_quota=5000000,
        token_version=1,
    )
    db_session.add(owner)
    await db_session.flush()

    pref = UserVoicePreference(user_id=owner.id)
    db_session.add(pref)
    await db_session.commit()
    await db_session.refresh(owner)
    return owner

@pytest_asyncio.fixture
def owner_token(test_owner: User) -> str:
    return create_access_token(test_owner.id, test_owner.email, test_owner.role.value, token_version=test_owner.token_version)

