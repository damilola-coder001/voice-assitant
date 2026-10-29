"""
Script to update credentials for Owner, Admin, and User roles,
bump token_version to immediately invalidate all existing sessions,
and reset failed login attempts / lockouts.
"""
import os
import sys
sys.path.insert(0, os.path.abspath("."))
import sqlite3
from app.security.passwords import hash_password

NEW_CREDENTIALS = {
    "owner@nore.ai": "NoreOwner#2026!Master",
    "admin@nore.ai": "NoreAdmin#2026!Control",
    "user@nore.ai": "NoreUser#2026!Client",
}

def update_users():
    conn = sqlite3.connect("voice_assistant.db")
    c = conn.cursor()

    print("[*] Updating credentials and invalidating active sessions in voice_assistant.db...")
    for email, plain_pw in NEW_CREDENTIALS.items():
        hashed = hash_password(plain_pw)
        c.execute("""
            UPDATE users 
            SET hashed_password = ?,
                token_version = token_version + 10,
                failed_login_attempts = 0,
                locked_until = NULL,
                is_active = 1,
                status = 'active'
            WHERE email = ?
        """, (hashed, email))
        print(f"  [+] {email}: updated (rows affected: {c.rowcount})")

    conn.commit()

    c.execute("SELECT id, email, role, is_active, token_version FROM users")
    users = c.fetchall()
    print("[*] Current state of users in DB:")
    for u in users:
        print(f"    - ID: {u[0]}, Email: {u[1]}, Role: {u[2]}, Active: {u[3]}, Token Version: {u[4]}")

    conn.close()
    print("[OK] All credentials updated and all previous sessions successfully invalidated.")

if __name__ == "__main__":
    update_users()
