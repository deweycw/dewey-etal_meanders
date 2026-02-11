"""
PFLOTRAN Processing Module — thin wrapper around pflotranutils.processor.

Sets project_root so that relative path resolution works for this repository.
"""

from pathlib import Path

from pflotranutils.processor import PflotranProcessor, _resolve_path  # noqa: F401

# Set class-level project root for this repo
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PflotranProcessor.PROJECT_ROOT = _PROJECT_ROOT
