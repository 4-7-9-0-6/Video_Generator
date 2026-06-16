"""Test config — isolate the DB/assets into a temp dir BEFORE importing app modules."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="toonforge_test_"))
os.environ["TOONFORGE_DATA_DIR"] = str(_TMP / "data")
os.environ["TOONFORGE_DB_PATH"] = str(_TMP / "data" / "test.sqlite3")
# keep providers deterministic/offline for the default test run, isolated from the dev's .env
os.environ.setdefault("PROVIDER_IMAGE", "pollinations")
os.environ.setdefault("PROVIDER_LLM", "mock")
os.environ.setdefault("PROVIDER_VIDEO", "")   # default = Ken Burns; don't inherit .env's choice
