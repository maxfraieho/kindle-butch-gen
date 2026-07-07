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

def get_pdf_page_count(pdf_path):
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
    return 10  # Fallback

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
        marker_percent = (completed_marker_pages / total_pages * 100) if total_pages > 0 else 0.0
    
    # 2. Translation Progress
    should_translate = paths["target_lang"] != paths["source_lang"]
    if not should_translate or not has_pdf or not page_ranges:
        translation_percent = 100.0
    else:
        translate_cache = {}
        if os.path.exists(paths["translate_cache"]):
            try:
                with open(paths["translate_cache"], "r", encoding="utf-8") as f:
                    translate_cache = json.load(f)
            except Exception:
                pass
                
        completed_trans_pages = 0.0
        pm = PlaceholderManager()
        pdf_basename = os.path.splitext(os.path.basename(pdf_path))[0]
        total_pages = sum(end - start + 1 for start, end in page_ranges)
        
        for start, end in page_ranges:
            batch_out_dir = os.path.join(paths["batches_dir"], f"batch_{start}_{end}")
            marker_out_subdir = os.path.join(batch_out_dir, pdf_basename)
            marker_md_file = os.path.join(marker_out_subdir, f"{pdf_basename}.md")
            
            if os.path.exists(marker_md_file) and os.path.getsize(marker_md_file) > 0:
                try:
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
    voice = paths.get("tts_voice", "ukrainian_tts")
    voice_quality = paths.get("tts_voice_quality", "medium")
    if voice == "ukrainian_tts" or voice_quality == "medium":
        model_filename = "uk_UA-ukrainian_tts-medium.onnx"
    else:
        model_filename = "uk_UA-lada-x_low.onnx"
    voice_slug = os.path.splitext(model_filename)[0]
    
    tts_cache_path = os.path.join(paths["cache_dir"], f"tts_cache_{voice_slug}.json")
    tts_cache = {}
    if os.path.exists(tts_cache_path):
        try:
            with open(tts_cache_path, "r", encoding="utf-8") as f:
                tts_cache = json.load(f)
        except Exception:
            pass
            
    chunks_dir = os.path.join(paths["audio_dir"], f"chunks_{voice_slug}")
    
    # Calculate directly from the merged markdown file if it exists
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
            for p in paragraphs:
                chunks = split_paragraph_to_chunks(p, max_chars=1000)
                for chunk in chunks:
                    chunk = chunk.strip()
                    if chunk:
                        chunk_texts.append(chunk)
            
            if chunk_texts:
                completed_chunks = 0
                for text in chunk_texts:
                    h = get_hash(text)
                    wav_file = os.path.join(chunks_dir, f"{h}.wav")
                    if h in tts_cache and os.path.exists(wav_file):
                        completed_chunks += 1
                tts_percent = (completed_chunks / len(chunk_texts) * 100)
            else:
                tts_percent = 100.0
        except Exception:
            tts_percent = 0.0
    else:
        # Fallback to 0 if the merged file does not exist yet
        tts_percent = 0.0
    
    return {
        "marker_percent": round(marker_percent, 1),
        "translation_percent": round(translation_percent, 1),
        "tts_percent": round(tts_percent, 1)
    }

def print_status(slug):
    res = calculate_progress(slug)
    if "error" in res:
        print(f"Error: {res['error']}")
        sys.exit(1)
    print(f"Marker: {res['marker_percent']}%")
    print(f"Translation: {res['translation_percent']}%")
    print(f"TTS: {res['tts_percent']}%")

def add_book(slug, pdf_path, title, authors, lang):
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
    
    dest_pdf = os.path.join(paths["book_dir"], f"{slug}.pdf")
    shutil.copy2(pdf_path, dest_pdf)
    
    pages = get_pdf_page_count(dest_pdf)
    
    config_data = {
        "slug": slug,
        "title": title,
        "authors": authors,
        "source_lang": "ru",
        "target_lang": lang,
        "pdf_path": f"books/{slug}/{slug}.pdf",
        "generate_audiobook": True,
        "tts_voice": "ukrainian_tts",
        "tts_voice_quality": "medium",
        "tts_speaker_id": 2,
        "tts_speed": 1.0,
        "tts_noise_scale": 0.667,
        "tts_noise_w": 0.8,
        "page_ranges": [[1, pages]]
    }
    
    with open(paths["config_path"], "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)
        
    print(f"Book '{slug}' added successfully with {pages} pages.")

