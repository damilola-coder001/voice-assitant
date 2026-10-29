from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.audit import SecurityAuditLog
from app.models.conversation import ConversationSession, Message
from app.models.user import RoleEnum, User
from app.schemas.conversation import (
    ConversationExport,
    MessageCreate,
    MessageRead,
    SessionBriefRead,
    SessionCreate,
    SessionRead,
    SessionUpdate,
)
from app.security.dependencies import get_current_user

router = APIRouter(prefix="/conversations", tags=["Conversations"])

@router.get("", response_model=List[SessionBriefRead])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all conversation sessions for the authenticated user."""
    query = (
        select(
            ConversationSession.id,
            ConversationSession.title,
            ConversationSession.persona_id,
            ConversationSession.created_at,
            ConversationSession.updated_at,
            func.count(Message.id).label("message_count"),
        )
        .outerjoin(Message, Message.session_id == ConversationSession.id)
        .where(ConversationSession.user_id == current_user.id)
        .group_by(ConversationSession.id)
        .order_by(ConversationSession.updated_at.desc())
    )
    result = await db.execute(query)
    rows = result.all()

    return [
        SessionBriefRead(
            id=r.id,
            title=r.title,
            persona_id=r.persona_id,
            created_at=r.created_at,
            updated_at=r.updated_at,
            message_count=r.message_count,
        )
        for r in rows
    ]

@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    data: SessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a new persistent conversation session."""
    session = ConversationSession(
        user_id=current_user.id,
        title=data.title or "New Voice Session",
        persona_id=data.persona_id or "executive",
        system_prompt=data.system_prompt,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    query = select(ConversationSession).where(ConversationSession.id == session.id).options(selectinload(ConversationSession.messages))
    result = await db.execute(query)
    return result.scalar_one()

@router.get("/{session_id}", response_model=SessionRead)
async def get_conversation(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve full conversation session and message history."""
    query = (
        select(ConversationSession)
        .where(ConversationSession.id == session_id)
        .options(selectinload(ConversationSession.messages))
    )
    result = await db.execute(query)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found.")

    if session.user_id != current_user.id:
        if current_user.role == RoleEnum.USER:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found.")

        # Administrative / Owner inspection is audited
        audit = SecurityAuditLog(
            event_type="sensitive_conversation_access",
            user_id=current_user.id,
            email=current_user.email,
            details=f"Principal {current_user.email} ({current_user.role.value}) accessed conversation #{session.id} belonging to user #{session.user_id}",
        )
        db.add(audit)
        await db.commit()

    return session

@router.put("/{session_id}", response_model=SessionRead)
async def update_conversation(
    session_id: int,
    data: SessionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update title or persona configuration of conversation."""
    query = select(ConversationSession).where(
        ConversationSession.id == session_id,
        ConversationSession.user_id == current_user.id,
    ).options(selectinload(ConversationSession.messages))
    result = await db.execute(query)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found.")

    if data.title is not None:
        session.title = data.title
    if data.persona_id is not None:
        session.persona_id = data.persona_id
    if data.system_prompt is not None:
        session.system_prompt = data.system_prompt

    await db.commit()
    await db.refresh(session)
    return session

@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a conversation session and all its messages."""
    result = await db.execute(
        select(ConversationSession).where(
            ConversationSession.id == session_id,
            ConversationSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found.")

    await db.delete(session)
    await db.commit()
    return None

@router.post("/{session_id}/messages", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
async def add_message(
    session_id: int,
    data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a message record to a conversation session."""
    result = await db.execute(
        select(ConversationSession).where(
            ConversationSession.id == session_id,
            ConversationSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found.")

    msg = Message(
        session_id=session_id,
        role=data.role,
        content=data.content,
        audio_url=data.audio_url,
        audio_duration_ms=data.audio_duration_ms,
        characters_count=data.characters_count or len(data.content),
        latency_ms=data.latency_ms,
        voice_id=data.voice_id,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg

@router.get("/{session_id}/export")
async def export_conversation(
    session_id: int,
    format: str = "json",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export conversation in JSON or Markdown format."""
    query = (
        select(ConversationSession)
        .where(ConversationSession.id == session_id)
        .options(selectinload(ConversationSession.messages))
    )
    result = await db.execute(query)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found.")

    if session.user_id != current_user.id:
        if current_user.role == RoleEnum.USER:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found.")

        audit = SecurityAuditLog(
            event_type="sensitive_conversation_export",
            user_id=current_user.id,
            email=current_user.email,
            details=f"Principal {current_user.email} ({current_user.role.value}) exported conversation #{session.id} belonging to user #{session.user_id}",
        )
        db.add(audit)
        await db.commit()

    if format.lower() == "markdown":
        md = [f"# {session.title}\n", f"**Persona:** {session.persona_id}  ", f"**Date:** {session.created_at.strftime('%Y-%m-%d %H:%M:%S')}  \n\n---\n"]
        for m in session.messages:
            sender = "User" if m.role == "user" else "Assistant"
            md.append(f"### {sender} ({m.created_at.strftime('%H:%M:%S')})\n{m.content}\n")
        return {"filename": f"conversation_{session_id}.md", "content": "\n".join(md), "format": "markdown"}

    # Default to structured JSON
    return ConversationExport(
        session_id=session.id,
        title=session.title,
        persona_id=session.persona_id,
        created_at=session.created_at,
        messages=[MessageRead.model_validate(m) for m in session.messages],
        export_format="json",
    )
