import os
import sys
from pathlib import Path

# Ensure VERCEL environment variable is set
os.environ["VERCEL"] = "1"

# Add project root directory to Python path
ROOT_DIR = Path(__file__).resolve().parent.parent
for p in [str(ROOT_DIR), "/var/task", os.getcwd()]:
    if p and p not in sys.path:
        sys.path.insert(0, p)

from app.main import app

# Expose both app and handler for maximum compatibility with Vercel ASGI runtime
handler = app
