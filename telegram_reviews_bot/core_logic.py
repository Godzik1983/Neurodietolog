import os
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


os.environ["PLATFORM_NAME"] = "telegram"
_SHARED_PATH = Path(__file__).resolve().parents[1] / "core_logic.py"
_SPEC = spec_from_file_location("shared_core_logic", _SHARED_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"Unable to load shared core logic from {_SHARED_PATH}")

_MODULE = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

for _name in dir(_MODULE):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_MODULE, _name)

__all__ = [name for name in globals() if not name.startswith("_")]
