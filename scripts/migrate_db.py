import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "voice_assistant.db"

def migrate():
    if not DB_PATH.exists():
        print("Database does not exist yet; create_all will handle it.")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(user_voice_preferences)")
    existing = {row[1] for row in cur.fetchall()}

    columns = [
        ("assistant_name", "VARCHAR(50) DEFAULT 'NORE'"),
        ("tone", "VARCHAR(50) DEFAULT 'balanced'"),
        ("formality", "VARCHAR(50) DEFAULT 'professional'"),
        ("response_style", "VARCHAR(50) DEFAULT 'adaptive'"),
        ("preferred_language", "VARCHAR(20) DEFAULT 'en'"),
    ]

    for name, definition in columns:
        if name not in existing:
            cur.execute(f"ALTER TABLE user_voice_preferences ADD COLUMN {name} {definition}")
            print(f"Added column {name} to user_voice_preferences.")

    conn.commit()
    conn.close()
    print("Database migration complete.")

if __name__ == "__main__":
    migrate()
