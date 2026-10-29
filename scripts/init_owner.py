import argparse
import asyncio
from pathlib import Path
import secrets
import sys

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.user import RoleEnum, User, UserVoicePreference
from app.security.passwords import hash_password
from app.config import settings

PREDICTABLE_PASSWORDS = {
    "admin", "password", "owner", "123456", "admin123", "owner123",
    "password123", "changeme", "secret", "root", "default"
}

async def initialize_owner(email: str, password: str, full_name: str = "System Owner"):
    """Securely initialize the platform Owner principal."""
    email_clean = email.strip().lower()
    pwd_clean = password.strip()

    if len(pwd_clean) < 12:
        print("[ERROR] Password must be at least 12 characters long for the Owner account.")
        sys.exit(1)

    if pwd_clean.lower() in PREDICTABLE_PASSWORDS:
        print("[ERROR] Predictable passwords are strictly prohibited for the Owner role.")
        sys.exit(1)

    async with AsyncSessionLocal() as db:
        # Check if an Owner already exists
        result = await db.execute(select(User).where(User.role == RoleEnum.OWNER))
        existing_owner = result.scalars().first()

        if existing_owner:
            print(f"[!] Protected Rule: An Owner account already exists ({existing_owner.email}).")
            print("[!] The Owner role is unique and cannot be casually recreated or duplicated.")
            sys.exit(1)

        # Check if email is already taken by another account
        existing_email = await db.execute(select(User).where(User.email == email_clean))
        if existing_email.scalars().first():
            print(f"[ERROR] Email {email_clean} is already registered by an existing account.")
            sys.exit(1)

        # Create Owner principal
        hashed_pwd = hash_password(pwd_clean)
        owner_user = User(
            email=email_clean,
            hashed_password=hashed_pwd,
            full_name=full_name,
            role=RoleEnum.OWNER,
            status="active",
            is_active=True,
            daily_character_quota=5000000,  # Elevated quota for owner
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

        print("=" * 60)
        print(" [NORE PLATFORM SECURITY] OWNER ACCOUNT INITIALIZED")
        print("=" * 60)
        print(f" Owner Principal: {owner_user.email}")
        print(f" Role:            {owner_user.role.value.upper()} (Protected Principal)")
        print(f" User ID:         {owner_user.id}")
        print(" Status:          ACTIVE")
        print("-" * 60)
        print(" IMPORTANT: Keep these credentials secure. Once initialized, the")
        print(" Owner account cannot be deleted or demoted by administrators.")
        print("=" * 60)

def main():
    parser = argparse.ArgumentParser(description="NORE Platform Secure Owner Initialization CLI")
    parser.add_argument("--email", default=settings.OWNER_INITIAL_EMAIL or "owner@nore.ai", help="Owner email address")
    parser.add_argument("--password", default=None, help="Owner password (min 12 chars). If omitted, a high-entropy secret is generated.")
    parser.add_argument("--name", default="Platform Owner", help="Full name of Owner")

    args = parser.parse_args()

    password = args.password
    if not password:
        if settings.OWNER_INITIAL_PASSWORD and len(settings.OWNER_INITIAL_PASSWORD) >= 12 and settings.OWNER_INITIAL_PASSWORD.lower() not in PREDICTABLE_PASSWORDS:
            password = settings.OWNER_INITIAL_PASSWORD
        else:
            # Generate cryptographically secure high-entropy secret
            password = secrets.token_urlsafe(24)
            print(f"[*] Generated high-entropy password for Owner: {password}")

    asyncio.run(initialize_owner(email=args.email, password=password, full_name=args.name))

if __name__ == "__main__":
    main()
