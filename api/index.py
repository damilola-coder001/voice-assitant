import os
import sys
from pathlib import Path

# Ensure VERCEL environment variable is set
os.environ["VERCEL"] = "1"

# Add project root directory and task root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
CURRENT_DIR = Path(__file__).resolve().parent

for p in [str(ROOT_DIR), str(CURRENT_DIR), os.getcwd(), "/var/task"]:
    if p and p not in sys.path:
        sys.path.insert(0, p)

try:
    from app.main import app as application
    app = application
except Exception as e:
    import traceback
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    err_trace = traceback.format_exc()
    app = FastAPI(title="NORE Startup Error")

    @app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
    async def catch_all(full_path: str = ""):
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>NORE - Server Startup Diagnostic</title>
        <style>body {{ font-family: monospace; background: #0c0a09; color: #f5f5f4; padding: 2rem; }} pre {{ background: #1c1917; padding: 1rem; border-radius: 8px; color: #f87171; overflow-x: auto; }}</style>
        </head>
        <body>
        <h2>NORE Vercel Startup Diagnostic</h2>
        <p>FastAPI failed to initialize on Vercel Serverless with the following error:</p>
        <pre>{err_trace}</pre>
        <hr>
        <p><strong>CWD:</strong> {os.getcwd()}</p>
        <p><strong>sys.path:</strong> {sys.path}</p>
        </body>
        </html>
        """
        return HTMLResponse(content=html, status_code=500)
