#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import re
import json
import hashlib
import argparse
import requests
from common.text_protect import PlaceholderManager
from common.book_paths import resolve_book_paths

def log(message):
    print(f"[Translate] {message}", flush=True)

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
            # Split large paragraph by sentences
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

def translate_text(text, api_url, target_lang="uk", temperature=0.7):
    lang_map = {
        "uk": "Ukrainian",
        "ru": "Russian",
        "en": "English"
    }
    target_lang_full = lang_map.get(target_lang, "Ukrainian")
    prompt = f"Translate the following text into {target_lang_full}:\n\n{text}"
    headers = {"Content-Type": "application/json"}
    data = {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "top_p": 0.6,
        "top_k": 20,
        "repetition_penalty": 1.05,
        "max_tokens": 4096
    }
    
    try:
        response = requests.post(api_url, headers=headers, json=data, timeout=180)
        if response.status_code != 200:
            log(f"Error from llama-server: {response.status_code} - {response.text}")
            return None
        res_json = response.json()
        translated = res_json["choices"][0]["message"]["content"].strip()
        
        clean_prefixes = [
            f"here is the translation into {target_lang_full.lower()}:",
            f"переклад {target_lang_full.lower()}ською:",
            "translation:",
            "ось переклад:"
        ]
        for pref in clean_prefixes:
            if translated.lower().startswith(pref):
                translated = translated[len(pref):].strip()
        return translated
    except Exception as e:
        log(f"API request failed: {e}")
        return None

def validate_translation_segment(original, translated):
    # Count headers
    orig_headers = len([line for line in original.splitlines() if line.strip().startswith('#')])
    trans_headers = len([line for line in translated.splitlines() if line.strip().startswith('#')])
    
    if orig_headers != trans_headers:
        log(f"Validation failure: Headers count mismatch! Original: {orig_headers}, Translated: {trans_headers}")
        return False
        
    # Check placeholders
    orig_placeholders = set(re.findall(r"__[A-Z_]+_[0-9]+__", original))
    trans_placeholders = set(re.findall(r"__[A-Z_]+_[0-9]+__", translated))
    
    missing = orig_placeholders - trans_placeholders
    extra = trans_placeholders - orig_placeholders
    
    if missing or extra:
        log(f"Validation failure: Placeholders mismatch!")
        if missing:
            log(f"Missing in translation: {missing}")
        if extra:
            log(f"Extra in translation: {extra}")
        return False
        
    return True

def translate_segment_with_retry(segment, pm, api_url, target_lang="uk", max_retries=3):
    temp = 0.7
    for attempt in range(max_retries):
        if attempt > 0:
            temp = 0.1
            log(f"Retrying translation of segment (attempt {attempt+1}/{max_retries}) with temperature {temp}...")
            
        translated = translate_text(segment, api_url, target_lang=target_lang, temperature=temp)
        if not translated:
            continue
            
        translated = pm.normalize_placeholders(translated)
            
        if validate_translation_segment(segment, translated):
            return translated
        else:
            log(f"Segment validation failed on attempt {attempt+1}.")
            
    log("Warning: Segment translation validation failed after all retries. Proceeding with last translation.")
    return translated

def main():
    parser = argparse.ArgumentParser(description="Markdown translation module via llama-server")
    parser.add_argument("--input", "-i", required=False, help="Input Markdown file")
    parser.add_argument("--output", "-o", required=False, help="Output Markdown file")
    parser.add_argument("--api-url", default="http://localhost:8081/v1/chat/completions", help="Llama server API endpoint")
    parser.add_argument("--cache", default=None, help="Cache file for progress tracking")
    parser.add_argument("--book", "-b", help="Book slug")
    parser.add_argument("--config", "-c", help="Book configuration JSON path")
    parser.add_argument("--target-lang", "-t", default="uk", help="Target language (default: uk)")
    args = parser.parse_args()
    
    if not args.input and not args.book and not args.config:
        parser.error("At least one of --input, --book, or --config must be specified.")
        
    repo_dir = os.path.dirname(os.path.abspath(__file__))
    
    slug = args.book
    if not slug and args.config:
        try:
            with open(args.config, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                slug = cfg.get("slug")
        except Exception:
            pass
    if not slug:
        slug = "default-book"
        
    paths = resolve_book_paths(repo_dir, slug, config_path=args.config)
    
    input_path = args.input
    if not input_path:
        input_path = os.path.join(paths["book_dir"], "input", "input.md")
        
    output_path = args.output
    if not output_path:
        output_path = os.path.join(paths["output_dir"], "output.md")
        
    cache_path = args.cache
    if not cache_path:
        if args.book or args.config:
            cache_path = paths["translate_cache"]
        else:
            cache_path = "progress_translate.json"
            
    target_lang = args.target_lang
    if paths.get("target_lang"):
        target_lang = paths["target_lang"]
        
    # Ensure directories exist
    os.makedirs(os.path.dirname(os.path.abspath(input_path)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
    
    if not os.path.exists(input_path):
        log(f"Error: Input file '{input_path}' does not exist.")
        sys.exit(1)
        
    # Test api-url connectivity
    try:
        test_url = args.api_url.replace("/chat/completions", "").replace("/v1", "")
        res = requests.get(test_url, timeout=5)
        log(f"Connected to translation server at {test_url}")
    except Exception as e:
        log(f"Error: Translation server at {args.api_url} is not reachable: {e}")
        log("Please start the translation server using:")
        log("llama-server -m ~/models/hy-mt2/Hy-MT2-1.8B-Q6_K.gguf -c 4096 -t 8 --port 8081")
        sys.exit(1)
        
    log(f"Reading source file: {input_path}")
    with open(input_path, "r", encoding="utf-8") as f:
        source_text = f.read()
        
    log("Protecting Markdown elements with placeholders...")
    pm = PlaceholderManager()
    protected_text = pm.protect(source_text)
    
    log("Splitting text into logical segments...")
    segments = split_into_segments(protected_text)
    log(f"Total segments to translate: {len(segments)}")
    
    # Load cache
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as cf:
                cache = json.load(cf)
            log(f"Loaded cache from {cache_path} with {len(cache)} entries.")
        except Exception as e:
            log(f"Warning: Failed to load cache: {e}. Starting fresh.")
            
    translated_segments = []
    
    for idx, seg in enumerate(segments):
        seg_hash = get_hash(seg)
        if seg_hash in cache:
            translated_segments.append(cache[seg_hash])
        else:
            log(f"Translating segment {idx+1}/{len(segments)} (length: {len(seg)} chars)...")
            translated_seg = translate_segment_with_retry(seg, pm, args.api_url, target_lang=target_lang)
            if not translated_seg:
                log(f"Critical error: Failed to translate segment {idx+1}. Using original segment to avoid crash.")
                translated_seg = seg
            translated_segments.append(translated_seg)
            # Save to cache
            cache[seg_hash] = translated_seg
            try:
                with open(cache_path, "w", encoding="utf-8") as cf:
                    json.dump(cache, cf, ensure_ascii=False, indent=2)
            except Exception as e:
                log(f"Warning: Failed to save cache: {e}")
                
    log("Merging translated segments...")
    translated_protected_text = "\n\n".join(translated_segments)
    
    log("Restoring placeholders...")
    final_text = pm.restore(translated_protected_text)
    
    # Write to output
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_text)
    log(f"Translation completed successfully! Saved to: {output_path}")

if __name__ == "__main__":
    main()
