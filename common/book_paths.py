import os
import json

def load_book_config(config_path):
    if not config_path or not os.path.exists(config_path):
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Paths] Warning: Failed to load config at {config_path}: {e}")
        return {}

def resolve_book_paths(repo_dir, slug, config_path=None):
    book_dir = os.path.join(repo_dir, "books", slug)
    if not config_path:
        config_path = os.path.join(book_dir, "config.json")
    
    config = load_book_config(config_path)
    
    target_lang = config.get("target_lang", "uk")
    source_lang = config.get("source_lang", "ru")
    title = config.get("title", slug)
    authors = config.get("authors", "Unknown")
    
    # PDF input file default: books/<slug>/<slug>.pdf
    pdf_path = config.get("pdf_path")
    if not pdf_path:
        pdf_path = os.path.join(book_dir, f"{slug}.pdf")
    
    # Cover file default: books/<slug>/cover.jpeg
    cover_path = config.get("cover")
    if not cover_path:
        cover_path = os.path.join(book_dir, "cover.jpeg")
    elif not os.path.isabs(cover_path):
        # Resolve relative to repo root or book folder
        candidate1 = os.path.join(repo_dir, cover_path)
        if os.path.exists(candidate1):
            cover_path = candidate1
        else:
            cover_path = os.path.join(book_dir, cover_path)

    paths = {
        "book_dir": book_dir,
        "config_path": os.path.abspath(config_path),
        "pdf_path": os.path.abspath(pdf_path),
        "cover_path": os.path.abspath(cover_path),
        "cache_dir": os.path.join(book_dir, "cache"),
        "translate_cache": os.path.join(book_dir, "cache", "translate_cache.json"),
        "batches_dir": os.path.join(book_dir, "batches"),
        "translated_dir": os.path.join(book_dir, "translated"),
        "output_dir": os.path.join(book_dir, "output"),
        "audio_dir": os.path.join(book_dir, "audio"),
        "log_path": os.path.join(book_dir, "conversion_progress.log"),
        
        # Metadata values
        "slug": slug,
        "title": title,
        "authors": authors,
        "target_lang": target_lang,
        "source_lang": source_lang,
        "page_ranges": config.get("page_ranges", []),
        "generate_audiobook": config.get("generate_audiobook", False),
        "tts_voice": config.get("tts_voice", "lada"),
        "tts_voice_quality": config.get("tts_voice_quality", "x_low"),
        "tts_speaker_id": int(config.get("tts_speaker_id", 2)),
        "tts_speed": float(config.get("tts_speed", 1.0)),
        "tts_noise_scale": float(config.get("tts_noise_scale", 0.667)),
        "tts_noise_w": float(config.get("tts_noise_w", 0.8)),
    }
    return paths

