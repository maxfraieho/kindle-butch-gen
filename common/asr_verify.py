#!/usr/bin/env python3
"""
common/asr_verify.py  —  TASK-86: ASR-петля верифікації наголосів

Standalone-модуль.  НЕ інтегрований у audio_stage.py (чекає підтвердження Q
щодо реального встановлення whisper.cpp / sherpa-onnx-whisper-model).

Призначення:
  Після TTS-синтезу чанка — транскрибувати аудіо через `whisper-cli` (або
  сумісний бінарник: sherpa-onnx-offline-asr, будь-який CLI з --file → stdout),
  порівняти з оригінальним текстом через Левенштейна, і повернути mismatch_flag
  у форматі quality_flags.json (той самий патерн, що translate_manga.py →
  post_render_check → quality_flags.json; TASK-19/20).

Аlternative backend:
  sherpa-onnx (Python package) вже встановлений на пристрої Q (версія 1.13.4,
  підтримує OfflineRecognizer.from_whisper()).  Коли буде завантажена ONNX-модель
  Whisper Small (доступна у репозиторії k2-fsa/sherpa-onnx), цей модуль може
  бути розширений без нового CLI-бінарника — достатньо замінити `transcribe()`
  або додати `transcribe_via_sherpa_onnx()`.  Потребує окремого підтвердження Q.

Безпека:
  Жоден важкий процес (компіляція, завантаження моделі, inference) не
  запускається при import цього модуля.  subprocess-виклик відбувається ТІЛЬКИ
  в `transcribe()`, і тільки якщо явно передати шлях до існуючого бінарника.

Формат mismatch_flag (відповідає quality_flags.json):
  {
    "chunk_id":       "slug_chunkXX",   # str  —  ідентифікатор чанка
    "audio_path":     "...",            # str  —  шлях до WAV/MP3
    "original_text":  "...",            # str  —  оригінал (після TTS-підготовки)
    "transcribed_text": "...",          # str  —  що почув ASR
    "levenshtein_distance": 12,         # int
    "char_error_rate":  0.15,           # float  —  CER = edit_dist / max(len_ref, 1)
    "mismatch":       True,             # bool  —  True якщо CER > threshold
    "reason":         "asr_mismatch",   # str  —  константа для фільтрації
    "cer_threshold":  0.15,             # float  —  поріг на момент перевірки
    "asr_backend":    "whisper-cli",    # str  —  "whisper-cli" | "sherpa-onnx" | "mock"
    "asr_model":      "...",            # str  —  шлях до моделі або назва
  }
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from typing import Optional

# ---------------------------------------------------------------------------
# Levensht ein — чиста Python-реалізація (без залежностей)
# Перевірено: python-Levenshtein / rapidfuzz НЕ використовуються у проєкті,
# тому додаємо власну O(n*m) реалізацію (достатньо для рядків < 1000 символів).
# ---------------------------------------------------------------------------

def levenshtein_distance(s1: str, s2: str) -> int:
    """Classic DP Levenshtein.  O(len(s1) * len(s2)) time and space.

    For short TTS chunk texts (< 500 chars) this is fast enough.
    If s1 or s2 is empty — returns len of the other (insert/delete all).
    """
    if s1 == s2:
        return 0
    len1, len2 = len(s1), len(s2)
    if len1 == 0:
        return len2
    if len2 == 0:
        return len1

    # Two-row rolling array to save memory
    prev = list(range(len2 + 1))
    curr = [0] * (len2 + 1)
    for i, c1 in enumerate(s1, 1):
        curr[0] = i
        for j, c2 in enumerate(s2, 1):
            if c1 == c2:
                curr[j] = prev[j - 1]
            else:
                curr[j] = 1 + min(prev[j], curr[j - 1], prev[j - 1])
        prev, curr = curr, prev
    return prev[len2]


def char_error_rate(ref: str, hyp: str) -> float:
    """CER = levenshtein_distance / max(len(ref), 1).

    Returns float in [0, ∞).  Values > 1.0 mean the ASR produced more
    characters than the reference (happens with hallucinations).
    """
    return levenshtein_distance(ref, hyp) / max(len(ref), 1)


# ---------------------------------------------------------------------------
# Нормалізація тексту перед порівнянням
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Strip extra whitespace and lower-case for comparison only.

    Does NOT modify Ukrainian stress marks (´) so the comparison works
    both with and without accent marks in the transcribed output.
    """
    import re
    text = text.strip()
    # Collapse multiple spaces/newlines to single space
    text = re.sub(r"\s+", " ", text)
    return text.lower()


# ---------------------------------------------------------------------------
# Транскрипція через whisper-cli subprocess
# ---------------------------------------------------------------------------

def transcribe(
    audio_path: str,
    whisper_cli_path: str,
    model_path: str,
    extra_args: Optional[list[str]] = None,
    timeout_seconds: int = 120,
    language: str = "uk",
) -> str:
    """Call whisper-cli (or compatible binary) and return transcribed text.

    Args:
        audio_path:      Existing WAV file to transcribe.
        whisper_cli_path: Absolute path to the whisper-cli binary.
                          Example: "/data/data/com.termux/files/home/whisper.cpp/whisper-cli"
                          The binary does NOT need to exist at import time —
                          FileNotFoundError is raised only when this function is called.
        model_path:      Path to the .gguf or .bin Whisper model.
        extra_args:      Additional CLI flags, e.g. ["--threads", "4"].
        timeout_seconds: Hard kill timeout.  For phone Q: 120s is conservative
                         for Short (< 10s) audio chunks.
        language:        Whisper language code (default "uk" for Ukrainian).

    Returns:
        Transcribed text as a plain string (stdout, stripped).

    Raises:
        FileNotFoundError: if whisper_cli_path or audio_path does not exist.
        subprocess.TimeoutExpired: if transcription exceeds timeout_seconds.
        subprocess.CalledProcessError: if binary exits non-zero.

    Expected whisper-cli interface (whisper.cpp ≥ 1.5):
        whisper-cli -m <model> -f <audio> -l <lang> --no-timestamps -otxt
    The binary prints transcription to stdout (with -otxt or plain).
    Adjust extra_args if your binary version uses different flags.
    """
    if not os.path.isfile(whisper_cli_path):
        raise FileNotFoundError(
            f"whisper-cli binary not found: {whisper_cli_path}\n"
            "Install via: pkg install whisper-cpp  (if available)  OR\n"
            "  compile whisper.cpp manually (requires Q confirmation — see TASK-86 safety constraints)\n"
            "  OR use sherpa-onnx Python backend (already installed, model not yet downloaded)."
        )
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    cmd = [
        whisper_cli_path,
        "-m", model_path,
        "-f", audio_path,
        "-l", language,
        "--no-timestamps",
        "-otxt",
    ]
    if extra_args:
        cmd.extend(extra_args)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=True,
    )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Побудова mismatch_flag (якісний формат quality_flags.json)
# ---------------------------------------------------------------------------

def build_mismatch_flag(
    chunk_id: str,
    audio_path: str,
    original_text: str,
    transcribed_text: str,
    cer_threshold: float = 0.15,
    asr_backend: str = "whisper-cli",
    asr_model: str = "",
) -> dict:
    """Build a mismatch_flag dict for quality_flags.json / stress review queue.

    The format mirrors translate_manga.py's post_render_check() flags:
    {
      "chunk_id": ..., "reason": "asr_mismatch",
      "mismatch": True/False, "char_error_rate": float, ...
    }

    A flag is always returned (mismatch=False if CER ≤ threshold).
    The caller decides whether to append to the queue (typically: only if
    mismatch=True, but keeping all flags is also valid for auditing).

    Args:
        chunk_id:        Unique identifier for this TTS chunk.
        audio_path:      Path to the synthesized WAV (for reference/playback).
        original_text:   The text that was fed to TTS.
        transcribed_text: The text returned by the ASR backend.
        cer_threshold:   CER above which mismatch=True.  Default 0.15 (15%).
        asr_backend:     Informational: "whisper-cli" | "sherpa-onnx" | "mock".
        asr_model:       Informational: model path or name used.

    Returns:
        dict with keys matching the format docstring at module top.
    """
    ref = _normalize(original_text)
    hyp = _normalize(transcribed_text)
    dist = levenshtein_distance(ref, hyp)
    cer = char_error_rate(ref, hyp)
    is_mismatch = cer > cer_threshold

    return {
        "chunk_id": chunk_id,
        "audio_path": audio_path,
        "original_text": original_text,
        "transcribed_text": transcribed_text,
        "levenshtein_distance": dist,
        "char_error_rate": round(cer, 4),
        "mismatch": is_mismatch,
        "reason": "asr_mismatch" if is_mismatch else "asr_ok",
        "cer_threshold": cer_threshold,
        "asr_backend": asr_backend,
        "asr_model": asr_model,
    }


# ---------------------------------------------------------------------------
# Запис черги у JSON-файл (аналог quality_flags.json для audio-пайплайну)
# ---------------------------------------------------------------------------

def append_to_stress_queue(flag: dict, queue_path: str) -> None:
    """Append a mismatch_flag to the stress review queue JSON file.

    The queue file is a JSON array (same convention as quality_flags.json).
    If the file does not exist, it is created.  Thread-unsafe (single-process
    assumption, same as quality_flags.json usage elsewhere in the project).

    Args:
        flag:       Dict returned by build_mismatch_flag().
        queue_path: Path to the JSON queue file, e.g.
                    "books/<slug>/asr_stress_queue.json"
    """
    if os.path.exists(queue_path):
        with open(queue_path, "r", encoding="utf-8") as f:
            try:
                queue = json.load(f)
                if not isinstance(queue, list):
                    queue = []
            except (json.JSONDecodeError, ValueError):
                queue = []
    else:
        queue = []

    queue.append(flag)

    with open(queue_path, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# High-level verify function: транскрибувати + побудувати flag в один виклик
# ---------------------------------------------------------------------------

def verify_chunk(
    chunk_id: str,
    audio_path: str,
    original_text: str,
    whisper_cli_path: str,
    model_path: str,
    cer_threshold: float = 0.15,
    language: str = "uk",
    extra_args: Optional[list[str]] = None,
    timeout_seconds: int = 120,
) -> dict:
    """Transcribe audio and build a mismatch_flag in one call.

    This is the main entry point for the ASR loop in audio_stage.py (future
    integration).  If transcription fails for any reason, returns a flag with
    transcribed_text="<error: ...>" and mismatch=True so the chunk is always
    queued for manual review on ASR failure (fail-safe, not fail-silent).

    Args:  (see transcribe() and build_mismatch_flag() for details)

    Returns:
        mismatch_flag dict.
    """
    try:
        transcribed = transcribe(
            audio_path=audio_path,
            whisper_cli_path=whisper_cli_path,
            model_path=model_path,
            extra_args=extra_args,
            timeout_seconds=timeout_seconds,
            language=language,
        )
        asr_backend = "whisper-cli"
    except Exception as exc:
        transcribed = f"<error: {exc}>"
        asr_backend = "whisper-cli-error"

    return build_mismatch_flag(
        chunk_id=chunk_id,
        audio_path=audio_path,
        original_text=original_text,
        transcribed_text=transcribed,
        cer_threshold=cer_threshold,
        asr_backend=asr_backend,
        asr_model=model_path,
    )
