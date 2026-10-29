from fastapi import APIRouter, Depends
from app.models.user import User
from app.schemas.admin import SecretScanResponse
from app.security.dependencies import require_admin
from app.security.secret_scanner import perform_secret_scan

router = APIRouter(prefix="/security", tags=["Security Monitoring"])

@router.post("/scan-secrets", response_model=SecretScanResponse)
async def scan_project_secrets(admin: User = Depends(require_admin)):
    """
    Trigger an automated security scan of project code, static assets, and templates
    to ensure no credentials or API keys have leaked.
    """
    scan_result = perform_secret_scan()
    return SecretScanResponse(
        scanned_files_count=scan_result["scanned_files_count"],
        findings_count=scan_result["findings_count"],
        status=scan_result["status"],
        findings=scan_result["findings"],
    )
