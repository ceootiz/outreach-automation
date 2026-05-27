from __future__ import annotations

import sys
import os
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault(
    "OUTREACH_AUTOMATION_APP_DIR",
    str(Path(tempfile.gettempdir()) / "outreach_automation_pytest"),
)
os.environ.setdefault("OUTREACH_AUTOMATION_DISABLE_ONBOARDING", "1")
