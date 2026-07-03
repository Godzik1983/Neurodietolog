import os
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


os.environ["PLATFORM_NAME"] = "max"


def _resolve_shared_path() -> Path:
    current = Path(__file__).resolve()
    candidates = [
        current.parent / "core_logic.py",
        current.parents[1] / "core_logic.py",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate != current:
            return candidate
    raise RuntimeError(f"Unable to locate shared core_logic.py for {current}")


_SHARED_PATH = _resolve_shared_path()
_SPEC = spec_from_file_location("shared_core_logic", _SHARED_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"Unable to load shared core logic from {_SHARED_PATH}")

_MODULE = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

for _name in dir(_MODULE):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_MODULE, _name)

__all__ = [name for name in globals() if not name.startswith("_")]


def get_whisper_model():
    return _MODULE.get_whisper_model()


def transcribe_audio_file(file_path: str) -> str:
    segments, _ = get_whisper_model().transcribe(file_path, language="ru", vad_filter=True)
    return " ".join((segment.text or "").strip() for segment in segments).strip()


if __name__ == "__main__":
    main()
