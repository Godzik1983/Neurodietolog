import os
import re
import shutil
import subprocess
import tempfile
import threading
import wave
from pathlib import Path
from typing import Any

import piper
from faster_whisper import WhisperModel
from num2words import num2words
from piper.config import SynthesisConfig
from piper.download_voices import download_voice
from piper.voice import PiperVoice

try:
    import pyttsx3  # type: ignore
    import pythoncom  # type: ignore
    HAS_PYTTSX3 = True
except Exception:
    pyttsx3 = None  # type: ignore
    pythoncom = None  # type: ignore
    HAS_PYTTSX3 = False

_MODEL: WhisperModel | None = None
_MODEL_LOCK = threading.Lock()
_TTS_LOCK = threading.Lock()
_PIPER_VOICE: PiperVoice | None = None
_PIPER_LOCK = threading.Lock()

PIPER_VOICE_NAME = os.getenv("PIPER_VOICE", "ru_RU-ruslan-medium")
PIPER_DIR = Path(os.getenv("PIPER_DIR", "voices"))
PIPER_ESPEAK_DIR = Path(piper.__file__).parent / "espeak-ng-data"
STT_MODEL_NAME = os.getenv("STT_MODEL", "tiny")
STT_CACHE_DIR = Path(os.getenv("STT_CACHE_DIR", "/tmp/.cache/faster-whisper"))
PIPER_LENGTH_SCALE = float(os.getenv("PIPER_LENGTH_SCALE", "1.22"))
PIPER_SENTENCE_SILENCE_MS = int(os.getenv("PIPER_SENTENCE_SILENCE_MS", "220"))

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\u2600-\u27BF"
    "]+",
    flags=re.UNICODE,
)
NUMBER_RE = re.compile(r"(?<!\w)-?\d+(?:[.,]\d+)?(?!\w)")


def _get_stt_model() -> WhisperModel:
    global _MODEL
    if _MODEL is None:
        with _MODEL_LOCK:
            if _MODEL is None:
                STT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                os.environ.setdefault("HF_HOME", str(STT_CACHE_DIR))
                os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(STT_CACHE_DIR))
                os.environ.setdefault("XDG_CACHE_HOME", str(STT_CACHE_DIR.parent))
                _MODEL = WhisperModel(
                    STT_MODEL_NAME,
                    device="cpu",
                    compute_type="int8",
                    download_root=str(STT_CACHE_DIR),
                )
    return _MODEL


def transcribe_audio_file(audio_path: str) -> str:
    model = _get_stt_model()
    segments, _ = model.transcribe(audio_path, language="ru", task="transcribe")
    text = " ".join(segment.text.strip() for segment in segments if segment.text).strip()
    return text


def _set_russian_voice(engine: Any) -> None:
    voices = engine.getProperty("voices") or []
    for voice in voices:
        voice_id = (getattr(voice, "id", "") or "").lower()
        voice_name = (getattr(voice, "name", "") or "").lower()
        languages = getattr(voice, "languages", []) or []
        lang_blob = " ".join(str(lang).lower() for lang in languages)

        if "ru" in voice_id or "russian" in voice_name or "ru" in lang_blob:
            engine.setProperty("voice", voice.id)
            return


def _prepare_tts_text(text: str) -> str:
    def _number_to_words(match: re.Match[str]) -> str:
        token = match.group(0)
        normalized = token.replace(",", ".")
        try:
            if "." in normalized:
                value = float(normalized)
            else:
                value = int(normalized)
            return num2words(value, lang="ru")
        except Exception:
            return token

    cleaned = (text or "").replace("\n", " ").strip()
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"[`*_~>#\[\]\(\)]", " ", cleaned)
    cleaned = EMOJI_RE.sub(" ", cleaned)
    cleaned = NUMBER_RE.sub(_number_to_words, cleaned)
    cleaned = cleaned.replace("_", " ")
    cleaned = re.sub(r"[^\w\s\-]", " ", cleaned, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _get_piper_voice() -> PiperVoice:
    global _PIPER_VOICE
    if _PIPER_VOICE is None:
        with _PIPER_LOCK:
            if _PIPER_VOICE is None:
                PIPER_DIR.mkdir(parents=True, exist_ok=True)
                model_path = PIPER_DIR / f"{PIPER_VOICE_NAME}.onnx"
                config_path = PIPER_DIR / f"{PIPER_VOICE_NAME}.onnx.json"
                if (not model_path.exists()) or (not config_path.exists()):
                    download_voice(PIPER_VOICE_NAME, PIPER_DIR)
                _PIPER_VOICE = PiperVoice.load(
                    model_path=model_path,
                    config_path=config_path,
                    espeak_data_dir=PIPER_ESPEAK_DIR,
                )
    return _PIPER_VOICE


def _synthesize_wav_piper(text: str) -> str:
    fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="tts_")
    os.close(fd)

    voice = _get_piper_voice()
    prepared_text = _prepare_tts_text(text)
    syn_config = SynthesisConfig(length_scale=PIPER_LENGTH_SCALE)
    chunks = list(voice.synthesize(prepared_text, syn_config=syn_config))
    if not chunks:
        raise RuntimeError("Piper returned empty audio")

    first = chunks[0]
    silence_frames = int(first.sample_rate * (PIPER_SENTENCE_SILENCE_MS / 1000.0))
    silence_bytes = b"\x00" * silence_frames * first.sample_width * first.sample_channels

    with wave.open(wav_path, "wb") as wav_file:
        wav_file.setnchannels(first.sample_channels)
        wav_file.setsampwidth(first.sample_width)
        wav_file.setframerate(first.sample_rate)
        for i, chunk in enumerate(chunks):
            wav_file.writeframes(chunk.audio_int16_bytes)
            if i < len(chunks) - 1 and silence_bytes:
                wav_file.writeframes(silence_bytes)

    return wav_path


def _synthesize_wav_pyttsx3(text: str) -> str:
    if not HAS_PYTTSX3:
        raise RuntimeError("pyttsx3/pythoncom is not available on this platform")

    fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="tts_")
    os.close(fd)
    with _TTS_LOCK:
        pythoncom.CoInitialize()
        try:
            engine = pyttsx3.init()
            _set_russian_voice(engine)
            rate = engine.getProperty("rate")
            engine.setProperty("rate", max(110, int(rate * 0.75)))
            engine.save_to_file(_prepare_tts_text(text), wav_path)
            engine.runAndWait()
        finally:
            pythoncom.CoUninitialize()
    return wav_path


def _synthesize_wav(text: str) -> str:
    try:
        return _synthesize_wav_piper(text)
    except Exception:
        return _synthesize_wav_pyttsx3(text)


def _convert_wav_to_ogg(wav_path: str) -> str | None:
    if not shutil.which("ffmpeg"):
        return None
    ogg_path = str(Path(wav_path).with_suffix(".ogg"))
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            wav_path,
            "-c:a",
            "libopus",
            "-b:a",
            "48k",
            ogg_path,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0 or not Path(ogg_path).exists():
        return None
    return ogg_path


def synthesize_speech(text: str) -> tuple[bytes, str, bool]:
    wav_path = _synthesize_wav(text)
    try:
        ogg_path = _convert_wav_to_ogg(wav_path)
        if ogg_path:
            try:
                return Path(ogg_path).read_bytes(), "response.ogg", True
            finally:
                Path(ogg_path).unlink(missing_ok=True)
        return Path(wav_path).read_bytes(), "response.wav", False
    finally:
        Path(wav_path).unlink(missing_ok=True)
