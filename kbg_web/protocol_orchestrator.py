"""
Protocol Orchestrator — computes the current stage of a book processing pipeline.
Defines 9 pipeline stages (Standard + Premium) and their status based on filesystem state.
"""
import os
import json
import glob
from copy import deepcopy

PIPELINE_STAGES = [
    {"id": "upload", "name": "Завантаження та витяг тексту", "tier": "standard", "icon": "upload",
     "description": "Завантаження EPUB/PDF, парсинг метаданих, витяг Markdown сегментів"},
    {"id": "cast_ner", "name": "Реєстр персонажів (NER)", "tier": "premium", "icon": "users",
     "description": "Автоматичне сканування перших 3-5 розділів моделлю Gemma 3 4B для визначення персонажів, їх роду та стилю мовлення"},
    {"id": "translation", "name": "Переклад тексту", "tier": "standard", "icon": "languages",
     "description": "Пакетний переклад з Tone CoT аналізом через Hy-MT2-7B з Live-корекціями тексту"},
    {"id": "mqm_review", "name": "Перевірка якості (MQM)", "tier": "premium", "icon": "shield-check",
     "description": "Багатовимірна оцінка якості перекладу 1-10 з виявленням пропусків та семантичних спотворень"},
    {"id": "ebook_compile", "name": "Компіляція eBook", "tier": "standard", "icon": "book-open",
     "description": "Конвертація перекладеного Markdown назад у EPUB та AZW3 через Calibre"},
    {"id": "nlp_stress", "name": "NLP обробка та наголоси", "tier": "standard", "icon": "type",
     "description": "Фільтрація не-мовленнєвих елементів, чанкінг тексту та розстановка граматичних наголосів (stressify)"},
    {"id": "audio_synth", "name": "Синтез аудіо (TTS)", "tier": "standard", "icon": "volume-2",
     "description": "Генерація аудіо через Supertonic 3 / StyleTTS2 з динамічними паузами"},
    {"id": "asr_verify", "name": "ASR верифікація наголосів", "tier": "premium", "icon": "mic",
     "description": "Whisper Small INT8 транскрибує аудіо, порівнює з текстом через CER (поріг 15%)"},
    {"id": "final_post", "name": "Фінальна обробка аудіо", "tier": "standard", "icon": "headphones",
     "description": "FFmpeg конкатенація, шумозаглушення, фільтри, кодування MP3"},
]


def _load_json(path):
    """Safely load JSON file, returning None on any error."""
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def _dir_has_files(dirpath, pattern="*"):
    """Check if directory exists and contains matching files."""
    if not os.path.isdir(dirpath):
        return False
    return len(glob.glob(os.path.join(dirpath, pattern))) > 0


def get_protocol_status(slug, data_dir="data"):
    """Compute the full protocol pipeline status for a book."""
    book_dir = os.path.join(data_dir, slug)
    if not os.path.isdir(book_dir):
        parent = os.path.dirname(os.path.abspath(data_dir))
        for candidate_name in ["books", "data"]:
            candidate_path = os.path.join(parent, candidate_name, slug)
            if os.path.isdir(candidate_path):
                book_dir = candidate_path
                break
    config = _load_json(os.path.join(book_dir, "config.json")) or {}
    progress = _load_json(os.path.join(book_dir, "progress.json")) or {}
    mqm_flags = _load_json(os.path.join(book_dir, "translation_quality_flags.json"))
    asr_flags = _load_json(os.path.join(book_dir, "asr_quality_flags.json"))
    cast_data = _load_json(os.path.join(book_dir, "cast_registry.json"))

    is_premium = config.get("premium", False) or config.get("mode") == "premium"
    is_running = config.get("is_running", False)
    active_stage_id = config.get("active_stage") or progress.get("active_stage")
    
    try:
        from kbg_web.status_helper import calculate_progress
        prog = calculate_progress(slug)
        if isinstance(prog, dict):
            progress.update(prog)
    except Exception:
        pass

    try:
        from kbg_web.app import is_book_process_running
        if is_book_process_running(slug):
            is_running = True
    except Exception:
        pass

    target_lang = config.get("target_lang", "uk")
    merged_md = os.path.join(book_dir, "translated", f"merged_translated_{target_lang}.md")
    if os.path.exists(merged_md):
        translation_pct = 100.0

    overall_pct = progress.get("overall_percent", 0)
    translation_pct = progress.get("translation_percent", 0)

    output_dir = os.path.join(book_dir, "output")
    stressed_dir = os.path.join(book_dir, "audio_chunks", "stressed")
    wav_dir = os.path.join(book_dir, "audio_chunks", "wav")

    stages = []
    current_stage = None
    found_active = False

    for stage_def in PIPELINE_STAGES:
        stage = deepcopy(stage_def)
        sid = stage["id"]

        # Default status
        status = "pending"

        # --- Determine status per stage ---
        if sid == "upload":
            if config.get("source_file") or config.get("title") or os.path.isdir(book_dir):
                status = "completed"

        elif sid == "cast_ner":
            if not is_premium:
                status = "skipped"
            elif cast_data and isinstance(cast_data.get("characters"), list) and len(cast_data["characters"]) > 0:
                status = "completed"
            elif is_running and active_stage_id == "cast_ner":
                status = "active"
            else:
                status = "pending"

        elif sid == "translation":
            if translation_pct >= 95:
                status = "completed"
            elif is_running and (active_stage_id in ("translation", "translate", None) and translation_pct > 0 and translation_pct < 95):
                status = "active"
            elif translation_pct > 0:
                status = "pending"

        elif sid == "mqm_review":
            if not is_premium:
                status = "skipped"
            elif mqm_flags is not None:
                status = "completed"
            elif is_running and active_stage_id == "mqm_review":
                status = "active"

        elif sid == "ebook_compile":
            has_epub = _dir_has_files(output_dir, "*.epub")
            has_azw3 = _dir_has_files(output_dir, "*.azw3")
            if has_epub or has_azw3:
                status = "completed"

        elif sid == "nlp_stress":
            if _dir_has_files(stressed_dir):
                status = "completed"
            elif is_running and active_stage_id in ("nlp_stress", "stressify", "stress"):
                status = "active"

        elif sid == "audio_synth":
            if _dir_has_files(wav_dir, "*.wav"):
                status = "completed"
            elif is_running and active_stage_id in ("audio_synth", "tts", "audio"):
                status = "active"

        elif sid == "asr_verify":
            if not is_premium:
                status = "skipped"
            elif asr_flags is not None:
                status = "completed"
            elif is_running and active_stage_id == "asr_verify":
                status = "active"

        elif sid == "final_post":
            if _dir_has_files(output_dir, "*.mp3"):
                status = "completed"
            elif is_running and active_stage_id in ("final_post", "concat", "post"):
                status = "active"

        stage["status"] = status

        if status == "active" and not found_active:
            current_stage = sid
            found_active = True

        stages.append(stage)

    # If no active stage found, find the first non-completed standard stage
    if not current_stage:
        for s in stages:
            if s["status"] in ("pending",) and s["tier"] == "standard":
                current_stage = s["id"]
                break

    return {
        "stages": stages,
        "current_stage": current_stage,
        "mode": "premium" if is_premium else "standard",
        "overall_progress": overall_pct,
        "book_title": config.get("title", slug),
        "book_slug": slug,
    }
