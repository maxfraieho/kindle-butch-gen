import os
import re
import json
import hashlib
import sys

# Resolve repo root directory
repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_dir not in sys.path:
    sys.path.insert(0, repo_dir)

from common.book_paths import resolve_book_paths
from common.text_protect import PlaceholderManager

def get_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def split_into_segments(text, max_chars=1200):
    paragraphs = text.split("\n\n")
    segments = []
    current_segment = []
    current_length = 0
    for p in paragraphs:
        p_len = len(p)
        if p_len > max_chars:
            if current_segment:
                segments.append("\n\n".join(current_segment))
                current_segment = []
                current_length = 0
            sentences = re.split(r'(?<=[.!?])\s+', p)
            curr_sent_group = []
            curr_sent_len = 0
            for s in sentences:
                if curr_sent_len + len(s) > max_chars:
                    if curr_sent_group:
                        segments.append(" ".join(curr_sent_group))
                    curr_sent_group = [s]
                    curr_sent_len = len(s)
                else:
                    curr_sent_group.append(s)
                    curr_sent_len += len(s) + 1
            if curr_sent_group:
                segments.append(" ".join(curr_sent_group))
        else:
            if current_length + p_len > max_chars:
                segments.append("\n\n".join(current_segment))
                current_segment = [p]
                current_length = p_len
            else:
                current_segment.append(p)
                current_length += p_len + 2
    if current_segment:
        segments.append("\n\n".join(current_segment))
    return segments

def split_paragraph_to_chunks(text, max_chars=1000):
    text = re.sub(r"__[A-Z_]+_\d+__", "", text)
    clean_text = PlaceholderManager.strip_formatting(text).strip()
    if not clean_text:
        return []
    if len(clean_text) <= max_chars:
        return [clean_text]
    sentences = re.split(r'(?<=[.!?])\s+', clean_text)
    chunks = []
    curr_group = []
    curr_len = 0
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > max_chars:
            if curr_group:
                chunks.append(" ".join(curr_group))
                curr_group = []
                curr_len = 0
            words = sentence.split(" ")
            word_group = []
            word_len = 0
            for w in words:
                if word_len + len(w) + 1 > max_chars:
                    if word_group:
                        chunks.append(" ".join(word_group))
                    word_group = [w]
                    word_len = len(w)
                else:
                    word_group.append(w)
                    word_len += len(w) + 1
            if word_group:
                chunks.append(" ".join(word_group))
        else:
            if curr_len + len(sentence) + (1 if curr_group else 0) > max_chars:
                if curr_group:
                    chunks.append(" ".join(curr_group))
                curr_group = [sentence]
                curr_len = len(sentence)
            else:
                curr_group.append(sentence)
                curr_len += len(sentence) + (1 if len(curr_group) > 1 else 0)
    if curr_group:
        chunks.append(" ".join(curr_group))
    return chunks

# Real incident, 2026-07-26: calculate_progress() (called for EVERY book on
# EVERY 5s dashboard poll via /api/books) re-derives the page count from
# scratch each time - re-parsing the PDF's xref/page-tree even though a
# book's page count never changes after upload. Measured contributing to
# sustained high CPU on the phone with nothing actually converting. Cache
# keyed by (path, mtime) so an edited/replaced file still gets re-counted.
_page_count_cache = {}


def get_pdf_page_count(pdf_path):
    try:
        mtime = os.path.getmtime(pdf_path)
    except OSError:
        mtime = None
    cache_key = (pdf_path, mtime)
    if mtime is not None and cache_key in _page_count_cache:
        return _page_count_cache[cache_key]
    count = _get_pdf_page_count_uncached(pdf_path)
    if mtime is not None:
        _page_count_cache[cache_key] = count
    return count


def _get_pdf_page_count_uncached(pdf_path):
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        return len(reader.pages)
    except ImportError:
        pass
    try:
        with open(pdf_path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 102400))
            tail = f.read()
            matches = re.findall(rb"/Count\s+(\d+)", tail)
            if matches:
                return int(matches[-1])
            f.seek(0)
            content = f.read()
            matches = re.findall(rb"/Count\s+(\d+)", content)
            if matches:
                return int(matches[-1])
    except Exception:
        pass
    raise RuntimeError(
        f"Could not determine page count for {pdf_path}: pypdf is not "
        "installed and no /Count marker was found in the raw PDF bytes "
        "(likely a compressed xref/object stream). Install pypdf "
        "(`pip install pypdf`) rather than guessing a page count, since a "
        "wrong guess silently truncates the whole book."
    )

# Real incident, 2026-07-26: the uncached function below re-derives
# translation progress by reading the FULL extracted book text, protecting
# placeholders, re-splitting it into segments (~550 for a real 374-page
# technical PDF), and hashing every single segment to check membership in
# translate_cache - then does an equivalent full re-chunk + per-chunk hash
# pass for TTS/stress progress. Measured live: 17-18 SECONDS per call for
# one book. list_books()/status_api() call this for EVERY book on EVERY 5s
# dashboard poll (see kbg_web/app.py) even when nothing is converting -
# the dominant cause of "opening the dashboard is unbearably slow".
# Cache keyed on the mtimes of every file whose content could change the
# result: unchanged mtimes (the common idle case) return the cached dict
# instantly; the moment translate_cache.json/tts_cache/etc actually change
# (a real conversion progressing) the key changes and it recomputes for
# real, so live progress during an active run still updates correctly.
_progress_cache = {}


def _progress_cache_key(slug, paths, book_dir):
    candidates = [
        paths.get("config_path"),
        os.path.join(paths.get("cache_dir", book_dir), "epub_progress.json"),
        os.path.join(book_dir, "manga_progress.json"),
        paths.get("translate_cache"),
    ]
    pdf_path = paths.get("pdf_path")
    page_ranges = paths.get("page_ranges") or []
    if pdf_path:
        pdf_basename = os.path.splitext(os.path.basename(pdf_path))[0]
        for start, end in page_ranges:
            batch_out_dir = os.path.join(paths["batches_dir"], f"batch_{start}_{end}")
            candidates.append(os.path.join(batch_out_dir, pdf_basename, f"{pdf_basename}.md"))
            candidates.append(os.path.join(batch_out_dir, "marker_run.log"))
    for voice_slug in ("styletts2", "supertonic-3-tts-int8"):
        candidates.append(os.path.join(paths.get("cache_dir", book_dir), f"tts_cache_{voice_slug}.json"))
    target_lang = paths.get("target_lang", "")
    source_lang = paths.get("source_lang", "")
    candidates.append(os.path.join(book_dir, "translated", f"stress_cache_{target_lang}.json"))
    translated_dir = paths.get("translated_dir", book_dir)
    candidates.append(os.path.join(translated_dir, f"merged_translated_{target_lang}.md"))
    candidates.append(os.path.join(translated_dir, f"merged_source_{source_lang}.md"))

    mtimes = []
    for f in candidates:
        if not f:
            continue
        try:
            mtimes.append((f, os.path.getmtime(f)))
        except OSError:
            mtimes.append((f, None))
    return (slug, tuple(mtimes))


def calculate_progress(slug):
    paths = resolve_book_paths(repo_dir, slug)
    book_dir = paths["book_dir"]
    if not os.path.exists(book_dir):
        return {
            "marker_percent": 0.0,
            "translation_percent": 0.0,
            "tts_percent": 0.0,
            "error": "Book directory does not exist"
        }

    cache_key = _progress_cache_key(slug, paths, book_dir)
    if cache_key in _progress_cache:
        return _progress_cache[cache_key]

    result = _calculate_progress_uncached(slug)
    _progress_cache[cache_key] = result
    # Drop stale entries for this slug so the dict doesn't grow forever
    # across a long conversion where the key changes on every real update.
    for k in [k for k in list(_progress_cache.keys()) if k[0] == slug and k != cache_key]:
        del _progress_cache[k]
    return result


def _calculate_progress_uncached(slug):
    paths = resolve_book_paths(repo_dir, slug)
    book_dir = paths["book_dir"]
    if not os.path.exists(book_dir):
        return {
            "marker_percent": 0.0,
            "translation_percent": 0.0,
            "tts_percent": 0.0,
            "error": "Book directory does not exist"
        }
        
    # Check if direct EPUB progress is available
    epub_prog_path = os.path.join(paths["cache_dir"], "epub_progress.json")
    if os.path.exists(epub_prog_path):
        try:
            with open(epub_prog_path, "r", encoding="utf-8") as f:
                ep = json.load(f)
                curr = ep.get("current_file", 0)
                tot = ep.get("total_files", 0)
                pct = ep.get("percent", 0.0)
            
            is_manga = False
            generate_audiobook = True
            config_path = paths["config_path"]
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as cf:
                        cfg_json = json.load(cf)
                        is_manga = cfg_json.get("is_manga", False)
                        generate_audiobook = cfg_json.get("generate_audiobook", True)
                except Exception:
                    pass
                    
            if is_manga:
                overall_percent = pct
            else:
                if generate_audiobook:
                    overall_percent = (100.0 + pct + 0.0 + 0.0) / 4
                else:
                    overall_percent = (100.0 + pct) / 2

            return {
                "is_manga": is_manga,
                "manga_percent": pct,
                "manga_pages_completed": curr,
                "manga_total_pages": tot,
                "marker_percent": 100.0,
                "translation_percent": pct,
                "stress_percent": 0.0,
                "tts_percent": 0.0,
                "overall_percent": round(overall_percent, 1)
            }
        except Exception:
            pass

    # Check if manga
    config_path = paths["config_path"]
    is_manga = False
    generate_audiobook = True
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                is_manga = cfg.get("is_manga", False)
                generate_audiobook = cfg.get("generate_audiobook", True)
        except Exception:
            pass
            
    if is_manga:
        manga_progress_path = os.path.join(book_dir, "manga_progress.json")
        manga_percent = 0.0
        curr = 0
        tot = 0
        if os.path.exists(manga_progress_path):
            try:
                with open(manga_progress_path, "r", encoding="utf-8") as f:
                    mp = json.load(f)
                    curr = mp.get("current_page", 0)
                    tot = mp.get("total_pages", 0)
                    if tot > 0:
                        manga_percent = round((curr / tot) * 100.0, 1)
            except Exception:
                pass
        return {
            "is_manga": True,
            "manga_percent": manga_percent,
            "manga_pages_completed": curr,
            "manga_total_pages": tot,
            "marker_percent": manga_percent,
            "translation_percent": manga_percent,
            "stress_percent": manga_percent,
            "tts_percent": manga_percent,
            "overall_percent": manga_percent
        }
    
    pdf_path = paths.get("pdf_path")
    has_pdf = pdf_path and os.path.exists(pdf_path)
    page_ranges = paths.get("page_ranges")
    
    # 1. Marker Progress
    if not has_pdf or not page_ranges:
        marker_percent = 100.0
    else:
        total_pages = sum(end - start + 1 for start, end in page_ranges)
        completed_marker_pages = 0
        pdf_basename = os.path.splitext(os.path.basename(pdf_path))[0]
        
        for start, end in page_ranges:
            batch_out_dir = os.path.join(paths["batches_dir"], f"batch_{start}_{end}")
            marker_out_subdir = os.path.join(batch_out_dir, pdf_basename)
            marker_md_file = os.path.join(marker_out_subdir, f"{pdf_basename}.md")
            if os.path.exists(marker_md_file) and os.path.getsize(marker_md_file) > 0:
                completed_marker_pages += (end - start + 1)
            else:
                marker_log = os.path.join(batch_out_dir, "marker_run.log")
                if os.path.exists(marker_log):
                    try:
                        with open(marker_log, "r", encoding="utf-8", errors="replace") as lf:
                            log_txt = lf.read()
                            matches = [int(m) for m in re.findall(r"(?:page|pg|p\.)\s*(\d+)", log_txt, re.IGNORECASE)]
                            valid_pages = [p for p in matches if start <= p <= end]
                            if valid_pages:
                                cur_p = max(valid_pages)
                                completed_marker_pages += max(0, cur_p - start + 1)
                    except Exception:
                        pass
        marker_percent = (completed_marker_pages / total_pages * 100) if total_pages > 0 else 0.0
    
    # 2. Translation Progress
    should_translate = paths["target_lang"] != paths["source_lang"]
    merged_translated = os.path.join(book_dir, "translated", f"merged_translated_{paths['target_lang']}.md")
    if not should_translate:
        translation_percent = 100.0
    elif not has_pdf or not page_ranges:
        if os.path.exists(merged_translated) and os.path.getsize(merged_translated) > 0:
            translation_percent = 100.0
        else:
            humanized_dir = os.path.join(book_dir, "humanized")
            translated_sub = os.path.join(book_dir, "translated")
            source_dir = os.path.join(book_dir, "source")
            if not os.path.exists(source_dir):
                source_dir = os.path.join(book_dir, "docs")

            hum_count = len([f for f in os.listdir(humanized_dir) if f.endswith(('.md', '.mdx'))]) if os.path.exists(humanized_dir) else 0
            trans_count = len([f for f in os.listdir(translated_sub) if f.endswith(('.md', '.mdx')) and not f.startswith('merged_')]) if os.path.exists(translated_sub) else 0

            completed_units = max(hum_count, trans_count)
            total_units = 0
            if os.path.exists(source_dir):
                total_units = len([f for f in os.listdir(source_dir) if f.endswith(('.md', '.mdx'))])

            if total_units == 0:
                cfg_path = paths["config_path"]
                if os.path.exists(cfg_path):
                    try:
                        with open(cfg_path, 'r', encoding='utf-8') as cf:
                            cdata = json.load(cf)
                            total_units = cdata.get("total_chunks") or cdata.get("total_chapters") or cdata.get("pdf_pages") or 0
                    except Exception:
                        pass

            if completed_units > 0 and total_units > 0:
                translation_percent = min(100.0, round((completed_units / total_units) * 100.0, 1))
            elif completed_units > 0:
                translation_percent = 99.0
            else:
                translation_percent = 0.0
    else:
        translate_cache = {}
        if os.path.exists(paths["translate_cache"]):
            try:
                with open(paths["translate_cache"], "r", encoding="utf-8") as f:
                    translate_cache = json.load(f)
            except Exception:
                pass
                
        completed_trans_pages = 0.0
        pdf_basename = os.path.splitext(os.path.basename(pdf_path))[0]
        total_pages = sum(end - start + 1 for start, end in page_ranges)
        
        for start, end in page_ranges:
            batch_out_dir = os.path.join(paths["batches_dir"], f"batch_{start}_{end}")
            marker_out_subdir = os.path.join(batch_out_dir, pdf_basename)
            marker_md_file = os.path.join(marker_out_subdir, f"{pdf_basename}.md")
            
            if os.path.exists(marker_md_file) and os.path.getsize(marker_md_file) > 0:
                try:
                    pm = PlaceholderManager()
                    with open(marker_md_file, "r", encoding="utf-8") as f:
                        text = f.read()
                    protected_text = pm.protect(text)
                    segments = split_into_segments(protected_text)
                    if segments:
                        completed_segs = sum(1 for seg in segments if get_hash(seg) in translate_cache)
                        fraction = completed_segs / len(segments)
                    else:
                        fraction = 1.0
                except Exception:
                    fraction = 0.0
                completed_trans_pages += (end - start + 1) * fraction
                
        translation_percent = (completed_trans_pages / total_pages * 100) if total_pages > 0 else 0.0

    # 3. TTS Progress
    tts_engine = paths.get("tts_engine", "supertonic3")
    if tts_engine == "styletts2":
        voice_slug = "styletts2"
    else:
        voice_slug = "supertonic-3-tts-int8"
    
    tts_cache_path = os.path.join(paths["cache_dir"], f"tts_cache_{voice_slug}.json")
    tts_cache = {}
    if os.path.exists(tts_cache_path):
        try:
            with open(tts_cache_path, "r", encoding="utf-8") as f:
                tts_cache = json.load(f)
        except Exception:
            pass
            
    chunks_dir = os.path.join(paths["audio_dir"], f"chunks_{voice_slug}")
    
    # 4. Stressifier Progress
    stress_cache_path = os.path.join(paths["book_dir"], "translated", f"stress_cache_{paths['target_lang']}.json")
    stress_cache = {}
    if os.path.exists(stress_cache_path):
        try:
            with open(stress_cache_path, "r", encoding="utf-8") as f:
                stress_cache = json.load(f)
        except Exception:
            pass

    suffix = f"_translated_{paths['target_lang']}" if (paths["target_lang"] != paths["source_lang"]) else ""
    if suffix:
        target_md_file = os.path.join(paths["translated_dir"], f"merged_translated_{paths['target_lang']}.md")
    else:
        target_md_file = os.path.join(paths["translated_dir"], f"merged_source_{paths['source_lang']}.md")

    if os.path.exists(target_md_file) and os.path.getsize(target_md_file) > 0:
        try:
            with open(target_md_file, "r", encoding="utf-8") as f:
                content = f.read()
            paragraphs = re.split(r'\n\s*\n', content)
            chunk_texts = []
            max_chunk_chars = 150 if tts_engine == "styletts2" else 1000
            for p in paragraphs:
                chunks = split_paragraph_to_chunks(p, max_chars=max_chunk_chars)
                for chunk in chunks:
                    chunk = chunk.strip()
                    if chunk:
                        chunk_texts.append(chunk)
            
            if chunk_texts:
                completed_chunks = 0
                completed_stress = 0
                for text in chunk_texts:
                    h = get_hash(text)
                    wav_file = os.path.join(chunks_dir, f"{h}.wav")
                    if h in tts_cache and os.path.exists(wav_file):
                        completed_chunks += 1
                    if h in stress_cache:
                        completed_stress += 1
                tts_percent = (completed_chunks / len(chunk_texts) * 100)
                stress_percent = (completed_stress / len(chunk_texts) * 100)
            else:
                tts_percent = 100.0
                stress_percent = 100.0
        except Exception:
            tts_percent = 0.0
            stress_percent = 0.0
    else:
        tts_percent = 0.0
        stress_percent = 0.0
    
    # Extract active stage details from conversion_progress.log
    active_stage_text = None
    log_path = os.path.join(book_dir, "conversion_progress.log")
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as lf:
                lines = lf.readlines()[-60:]
            current_seg = None
            total_segs = None
            batch_str = None
            for l in reversed(lines):
                if "Пауза" in l and "охолодження" in l:
                    active_stage_text = "🧊 Пауза між батчами (охолодження)..."
                    break
                m_seg = re.search(r"Переклад сегменту (\d+)/(\d+)", l)
                if m_seg and not current_seg:
                    current_seg = m_seg.group(1)
                    total_segs = m_seg.group(2)
                m_batch = re.search(r"\[Translate (\d+-\d+)\]", l) or re.search(r"блок (\d+/\d+)", l)
                if m_batch and not batch_str:
                    batch_str = m_batch.group(1)
                if current_seg and total_segs:
                    batch_info = f" (стор. {batch_str})" if batch_str else ""
                    active_stage_text = f"⚡ Переклад{batch_info}: {current_seg}/{total_segs} сегментів"
                    break
        except Exception:
            pass

    # Calculate overall percent
    if generate_audiobook:
        if tts_percent == 0.0 and stress_percent == 0.0 and translation_percent < 100.0:
            overall_percent = (marker_percent * 0.3) + (translation_percent * 0.7)
        else:
            overall_percent = (marker_percent + translation_percent + stress_percent + tts_percent) / 4
    else:
        overall_percent = (marker_percent + translation_percent) / 2

    return {
        "is_manga": False,
        "marker_percent": round(marker_percent, 1),
        "translation_percent": round(translation_percent, 1),
        "stress_percent": round(stress_percent, 1),
        "tts_percent": round(tts_percent, 1),
        "overall_percent": round(overall_percent, 1),
        "active_stage_text": active_stage_text
    }

def print_status(slug):
    res = calculate_progress(slug)
    if "error" in res:
        print(f"Error: {res['error']}")
        sys.exit(1)
    print(f"Marker: {res['marker_percent']}%")
    print(f"Translation: {res['translation_percent']}%")
    print(f"TTS: {res['tts_percent']}%")

def add_book(slug, pdf_path, title, authors, lang, source_lang="ru", is_manga=False):
    import shutil
    if not re.match(r"^[a-z0-9_-]+$", slug):
        raise ValueError("Invalid slug")
    
    paths = resolve_book_paths(repo_dir, slug)
    
    os.makedirs(paths["book_dir"], exist_ok=True)
    os.makedirs(paths["cache_dir"], exist_ok=True)
    os.makedirs(paths["batches_dir"], exist_ok=True)
    os.makedirs(paths["translated_dir"], exist_ok=True)
    os.makedirs(paths["output_dir"], exist_ok=True)
    os.makedirs(paths["audio_dir"], exist_ok=True)
    
    ext = os.path.splitext(pdf_path)[1].lower()
    dest_file = os.path.join(paths["book_dir"], f"{slug}{ext}")
    shutil.copy2(pdf_path, dest_file)
    
    if ext == ".pdf":
        pages = get_pdf_page_count(dest_file)
        page_ranges = [[0, pages - 1]] if pages > 0 else []
    else:
        pages = 0
        page_ranges = []
        
    config_data = {
        "slug": slug,
        "title": title,
        "authors": authors,
        "source_lang": source_lang,
        "target_lang": lang,
        "pdf_path": f"books/{slug}/{slug}.pdf" if ext == ".pdf" else "",
        "is_manga": is_manga,
        "generate_audiobook": not is_manga,
        "tts_voice": "ukrainian_tts" if lang == "uk" else "irina",
        "tts_voice_quality": "medium",
        "tts_speaker_id": 2 if lang == "uk" else 0,
        "tts_speed": 1.0,
        "tts_noise_scale": 0.667,
        "tts_noise_w": 0.8,
        "page_ranges": page_ranges
    }
    
    with open(paths["config_path"], "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)
        
    print(f"Book '{slug}' added successfully.")

