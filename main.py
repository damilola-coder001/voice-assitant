import sys
import traceback
from pathlib import Path

root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

try:
    from app.main import app  # noqa: E402, F401
except BaseException as exc:
    from fastapi import FastAPI  # noqa: E402
    from fastapi.responses import JSONResponse  # noqa: E402

    _err_msg = f"{type(exc).__name__}: {exc}"
    _err_tb = traceback.format_exc().splitlines()[-12:]
    app = FastAPI(title="NORE Diagnostic Fallback")

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
    async def _diagnostic_fallback(path: str):
        return JSONResponse(
            status_code=503,
            content={"status": "startup_error", "error": _err_msg, "traceback": _err_tb},
        )
