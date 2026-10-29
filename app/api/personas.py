from typing import List
from fastapi import APIRouter, Depends
from app.models.user import User
from app.schemas.persona import PersonaPreset
from app.security.dependencies import get_current_user
from app.services.conversational import conversational_engine

router = APIRouter(prefix="/personas", tags=["Personas"])

@router.get("", response_model=List[PersonaPreset])
async def list_personas(current_user: User = Depends(get_current_user)):
    """Retrieve all available assistant personas and their system configurations."""
    return conversational_engine.get_personas()
