import os
from pathlib import Path
from typing import Any, Dict, List

# Re-use logic from scripts/scan_secrets.py for in-app endpoint & tests
from scripts.scan_secrets import scan_file, EXCLUDED_DIRS, EXCLUDED_FILES

def perform_secret_scan(root_dir: Path = None) -> Dict[str, Any]:
    """Perform secret scan across workspace and return structured results."""
    if root_dir is None:
        root_dir = Path.cwd()

    findings_list = []
    scanned_count = 0

    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]
        for file in files:
            if file in EXCLUDED_FILES or file.endswith(".pyc") or file.endswith(".db"):
                continue
            file_path = Path(root) / file
            scanned_count += 1
            findings = scan_file(file_path)
            for line_num, label, snippet in findings:
                findings_list.append({
                    "file": str(file_path.relative_to(root_dir)),
                    "line": line_num,
                    "pattern": label,
                    "match": snippet,
                })

    return {
        "scanned_files_count": scanned_count,
        "findings_count": len(findings_list),
        "status": "clean" if len(findings_list) == 0 else "compromised",
        "findings": findings_list,
    }
