from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.voices import router as voices_router
from app.api.conversations import router as conversations_router
from app.api.personas import router as personas_router
from app.api.speech import router as speech_router
from app.api.admin import router as admin_router
from app.api.owner import router as owner_router
from app.api.security import router as security_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(voices_router)
api_router.include_router(conversations_router)
api_router.include_router(personas_router)
api_router.include_router(speech_router)
api_router.include_router(admin_router)
api_router.include_router(owner_router)
api_router.include_router(security_router)

__all__ = ["api_router"]
