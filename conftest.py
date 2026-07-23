"""Ensure the repo root is importable so tests can `import bareos_client` / `import app`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
