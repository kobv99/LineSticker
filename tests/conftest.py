"""Expose existing standalone skill scripts to regression tests."""
import sys
from pathlib import Path
SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "line-character-studio" / "scripts"
sys.path.insert(0, str(SCRIPTS))
