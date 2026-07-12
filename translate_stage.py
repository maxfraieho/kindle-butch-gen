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
from common.utils import get_hash, split_into_segments, to_xml_format

def log(message):
    print(f"[Translate] {message}", flush=True)


def to_prefix_format(text, pm):
    def repl(match):
        num = match.group(2)
        suffix = f"_{num}__"
        for key in pm.placeholders.keys():
            if key.endswith(suffix):
                return key
        return match.group(0)
    return re.sub(r"\[\s*([a-zA-Z]+)[-_\s]*(\d+)\s*\]", repl, text)

def _is_hy_mt2_model(base_url):
    """Detect if running model is Hy-MT2 by checking /props endpoint."""
    try:
        props_url = base_url.replace("/v1/chat/completions", "").replace("/completion", "")
        props_url = props_url.rstrip("/")
        resp = requests.get(f"{props_url}/props", timeout=5)
        if resp.status_code == 200:
            model_name = resp.json().get("model_alias", "") or resp.json().get("model", "")
            return "hy-mt2" in model_name.lower() or "hy_mt2" in model_name.lower()
    except Exception:
        pass
    # Also check /health for model path
    try:
        base = base_url.replace("/v1/chat/completions", "").replace("/completion", "").rstrip("/")
        slot_resp = requests.get(f"{base}/slots", timeout=5)
        if slot_resp.status_code == 200:
            slots = slot_resp.json()
            if slots and isinstance(slots, list):
                model_path = str(slots[0].get("model", ""))
                return "hy-mt2" in model_path.lower() or "hy_mt" in model_path.lower()
    except Exception:
        pass
    return False


def translate_text_hy_mt2(text, base_url, source_lang="ru", target_lang="uk", temperature=0.1):
    """Translate using Hy-MT2 raw /completion endpoint with correct chat tokens.
    
    Hy-MT2-7B chat template (from llama-server log):
      '<|startoftext|>system<|extra_4|>user<|extra_0|>reply<|eos|><|startoftext|>user<|extra_0|>'
    Hy-MT2-1.8B chat template:
      '<|hy_begin▁of▁sentence|><|hy_User|>...<|hy_Assistant|>'
    """
    lang_map = {
        "uk": "Ukrainian",
        "ru": "Russian",
        "en": "English"
    }
    source_lang_full = lang_map.get(source_lang, "Russian")
    target_lang_full = lang_map.get(target_lang, "Ukrainian")

    # Check llama-server /props to determine which version (7B vs 1.8B format)
    base = base_url.replace("/v1/chat/completions", "").replace("/completion", "").rstrip("/")
    is_7b_format = False
    try:
        props = requests.get(f"{base}/props", timeout=5).json()
        tmpl = props.get("chat_template", "") or props.get("model_alias", "")
        is_7b_format = "startoftext" in tmpl or "extra_0" in tmpl
    except Exception:
        pass

    if is_7b_format:
        # Hy-MT2-7B format: <|startoftext|>user<|extra_0|>reply<|eos|>
        raw_prompt = (
            f"<|startoftext|>Translate the following text from {source_lang_full} to {target_lang_full}. "
            f"Output ONLY the translation, no explanations, no commentary:\n\n{text}<|extra_0|>"
        )
        stop_tokens = ["<|eos|>", "<|startoftext|>", "<|extra_0|>"]
    else:
        # Hy-MT2-1.8B format
        raw_prompt = (
            f"<|hy_begin\u2581of\u2581sentence|>"
            f"<|hy_User|>Translate the following text from {source_lang_full} to {target_lang_full}. "
            f"Output only the translation, no explanations:\n\n{text}<|hy_Assistant|>"
        )
        stop_tokens = ["<|hy_User|>", "<|hy_begin\u2581of\u2581sentence|>", "<|endoftext|>"]

    completion_url = base_url.replace("/v1/chat/completions", "/completion").rstrip("/")
    if not completion_url.endswith("/completion"):
        completion_url = completion_url.rstrip("/") + "/completion"

    headers = {"Content-Type": "application/json"}
    data = {
        "prompt": raw_prompt,
        "temperature": temperature,
        "top_p": 0.95,
        "top_k": 20,
        "repetition_penalty": 1.05,
        "n_predict": 4096,
        "stop": stop_tokens
    }

    try:
        resp = requests.post(completion_url, headers=headers, json=data, timeout=300)
        if resp.status_code != 200:
            log(f"Hy-MT2 /completion error: {resp.status_code} - {resp.text[:200]}")
            return None
        result = resp.json()
        translated = result.get("content", "").strip()
        return translated if translated else None
    except Exception as e:
        log(f"Hy-MT2 API request failed: {e}")
        return None



def translate_text(text, api_url, target_lang="uk", temperature=0.7, source_lang="ru"):
    lang_map = {
        "uk": "Ukrainian",
        "ru": "Russian",
        "en": "English"
    }
    target_lang_full = lang_map.get(target_lang, "Ukrainian")

    # Auto-detect Hy-MT2 and use raw completion endpoint
    if _is_hy_mt2_model(api_url):
        log("Detected Hy-MT2 model — using raw /completion endpoint")
        return translate_text_hy_mt2(text, api_url, source_lang=source_lang,
                                     target_lang=target_lang, temperature=0.1)

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
        log(f"Original segment: {original!r}")
        log(f"Translated segment: {translated!r}")
        if missing:
            log(f"Missing in translation: {missing}")
        if extra:
            log(f"Extra in translation: {extra}")
        return False
        
    return True

def translate_segment_with_retry(segment, pm, api_url, target_lang="uk", max_retries=3):
    temp = 0.7
    xml_segment = to_xml_format(segment)
    orig_placeholders = set(re.findall(r"__[A-Z_]+_[0-9]+__", segment))
    last_translated = None
    
    for attempt in range(max_retries):
        if attempt > 0:
            temp = 0.1
            log(f"Retrying translation of segment (attempt {attempt+1}/{max_retries}) with temperature {temp}...")
            
        translated = translate_text(xml_segment, api_url, target_lang=target_lang, temperature=temp)
        if not translated:
            continue
            
        translated = to_prefix_format(translated, pm)
        translated = pm.normalize_placeholders(translated)
        
        last_translated = translated
            
        if validate_translation_segment(segment, translated):
            return translated
        else:
            log(f"Segment validation failed on attempt {attempt+1}.")
            
    # If all attempts failed, rescue by adjusting missing/extra placeholders
    if last_translated:
        trans_placeholders = set(re.findall(r"__[A-Z_]+_[0-9]+__", last_translated))
        missing = orig_placeholders - trans_placeholders
        extra = trans_placeholders - orig_placeholders
        
        rescued = last_translated
        if extra:
            log(f"Stripping extra placeholders from translation: {extra}")
            for ex in extra:
                rescued = rescued.replace(ex, "")
                
        if missing:
            log(f"Appending missing placeholders to translation: {missing}")
            rescued = rescued + " " + " ".join(sorted(list(missing)))
            
        if validate_translation_segment(segment, rescued):
            return rescued
            
    log("Warning: Segment validation failed after all retries. Falling back to ORIGINAL protected segment to preserve placeholders (images/links/code).")
    return segment

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
