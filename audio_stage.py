#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import re
import json
import hashlib
import argparse
import subprocess
from common.text_protect import PlaceholderManager
from common.book_paths import resolve_book_paths

def log(message):
    print(f"[AudioStage] {message}", flush=True)

def get_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def locate_translated_file(book_dir, target_lang):
    # Check 1: books/<slug>/translated/merged_translated_<target_lang>.md
    path1 = os.path.join(book_dir, "translated", f"merged_translated_{target_lang}.md")
    if os.path.exists(path1):
        return path1

    # Check 2: look for any .md file ending with _translated_<target_lang>.md under books/<slug>/translated/
    translated_dir = os.path.join(book_dir, "translated")
    if os.path.exists(translated_dir):
        for f in os.listdir(translated_dir):
            if f.endswith(f"_translated_{target_lang}.md"):
                return os.path.join(translated_dir, f)

    # Check 3: look under books/<slug>/output/
    output_dir = os.path.join(book_dir, "output")
    if os.path.exists(output_dir):
        for f in os.listdir(output_dir):
            if f.endswith(f"_translated_{target_lang}.md"):
                return os.path.join(output_dir, f)

    # Check 4: books/<slug>/translated/merged_source_{target_lang}.md
    path_source = os.path.join(book_dir, "translated", f"merged_source_{target_lang}.md")
    if os.path.exists(path_source):
        return path_source

    # Check 5: look for any .md file ending with _source_{target_lang}.md under books/<slug>/translated/
    if os.path.exists(translated_dir):
        for f in os.listdir(translated_dir):
            if f.endswith(f"_source_{target_lang}.md"):
                return os.path.join(translated_dir, f)

    # Check 6: look under books/<slug>/output/ for ending with _source_{target_lang}.md
    if os.path.exists(output_dir):
        for f in os.listdir(output_dir):
            if f.endswith(f"_source_{target_lang}.md"):
                return os.path.join(output_dir, f)

    return None

def split_paragraph_to_chunks(text, max_chars=1000):
    # Strip any stray placeholders of the form __PREFIX_ID__ BEFORE formatting is stripped
    text = re.sub(r"__[A-Z_]+_\d+__", "", text)
    # Strip formatting from paragraph first
    clean_text = PlaceholderManager.strip_formatting(text).strip()
    if not clean_text:
        return []

    # If within limit, return as single chunk
    if len(clean_text) <= max_chars:
        return [clean_text]

    # Split by sentence endings (. ! ?) followed by whitespace
    sentences = re.split(r'(?<=[.!?])\s+', clean_text)
    chunks = []
    curr_group = []
    curr_len = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # If a single sentence exceeds 1000 characters, chunk it by words
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
            # Check if adding the sentence would exceed the limit
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

def main():
    parser = argparse.ArgumentParser(description="Audio generation stage for translated books")
    parser.add_argument("--book", "-b", required=False, help="Book slug")
    parser.add_argument("--config", "-c", help="Optional path to config.json")
    args = parser.parse_args()

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
        log("Error: Book slug is required.")
        sys.exit(1)

    paths = resolve_book_paths(repo_dir, slug, config_path=args.config)
    target_lang = paths.get("target_lang", "uk")
    voice = paths.get("tts_voice", "lada")
    voice_quality = paths.get("tts_voice_quality", "x_low")
    speaker_id = paths.get("tts_speaker_id", 2)
    speed = paths.get("tts_speed", 1.0)
    noise_scale = paths.get("tts_noise_scale", 0.667)
    noise_w = paths.get("tts_noise_w", 0.8)

    # Pick voice based on voice and/or voice_quality config
    if voice == "ukrainian_tts" or voice_quality == "medium":
        model_filename = "uk_UA-ukrainian_tts-medium.onnx"
        url_base = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/uk/uk_UA/ukrainian_tts/medium/"
    else:
        model_filename = "uk_UA-lada-x_low.onnx"
        url_base = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/uk/uk_UA/lada/x_low/"

    model_dir = os.path.join(repo_dir, "models", "piper")
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, model_filename)

    # Automatic voice model download
    model_json_path = model_path + ".json"
    if not os.path.exists(model_path) or not os.path.exists(model_json_path):
        log(f"Model or config file not found. Downloading from Hugging Face...")
        for ext in ["", ".json"]:
            file_to_download = model_filename + ext
            url = url_base + file_to_download
            target_file_path = model_path + ext
            tmp_file_path = target_file_path + ".tmp"
            log(f"Downloading {url} to {tmp_file_path}...")
            
            cmd = ["curl", "-L", "-o", tmp_file_path, url]
            try:
                subprocess.run(cmd, check=True)
                os.rename(tmp_file_path, target_file_path)
                log(f"Successfully downloaded {file_to_download}")
            except subprocess.CalledProcessError as e:
                log(f"Error downloading {file_to_download}: {e}")
                if os.path.exists(tmp_file_path):
                    try:
                        os.remove(tmp_file_path)
                    except Exception:
                        pass
                sys.exit(1)

    model_path = os.path.abspath(model_path)
    voice_slug = os.path.splitext(os.path.basename(model_path))[0]

    # Set up directories
    book_dir = paths["book_dir"]
    chunks_dir = os.path.join(paths["audio_dir"], f"chunks_{voice_slug}")
    cache_path = os.path.join(paths["cache_dir"], f"tts_cache_{voice_slug}.json")
    output_dir = paths["output_dir"]

    os.makedirs(chunks_dir, exist_ok=True)
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    # Locate the translated markdown file
    translated_file = locate_translated_file(book_dir, target_lang)
    if not translated_file:
        log(f"Error: Could not locate translated markdown file for target language '{target_lang}' in '{book_dir}'")
        sys.exit(1)

    log(f"Using translated file: {translated_file}")

    # Read markdown and split into paragraphs
    with open(translated_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by double newlines
    paragraphs = re.split(r'\n\s*\n', content)
    log(f"Total paragraphs read: {len(paragraphs)}")

    # Clean formatting and split paragraphs if they exceed 1000 characters
    chunk_texts = []
    for p in paragraphs:
        chunks = split_paragraph_to_chunks(p, max_chars=1000)
        for chunk in chunks:
            chunk = chunk.strip()
            if chunk:
                chunk_texts.append(chunk)

    log(f"Total TTS text chunks to synthesize/verify: {len(chunk_texts)}")

    # Load TTS cache
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
            log(f"Loaded cache with {len(cache)} entries.")
        except Exception as e:
            log(f"Warning: Failed to load TTS cache: {e}. Starting fresh.")

    # Check for missing chunks
    missing_chunks = []
    chunk_hashes = []
    for text in chunk_texts:
        chunk_hash = get_hash(text)
        chunk_hashes.append(chunk_hash)
        
        wav_file = os.path.join(chunks_dir, f"{chunk_hash}.wav")
        # A chunk is valid if it is in cache AND the actual WAV file exists on disk
        if chunk_hash not in cache or not os.path.exists(wav_file):
            missing_chunks.append({
                "hash": chunk_hash,
                "text": text
            })

    # Keep only unique missing chunks for synthesis to avoid duplicate processing
    unique_missing_chunks = []
    seen_hashes = set()
    for mc in missing_chunks:
        if mc["hash"] not in seen_hashes:
            seen_hashes.add(mc["hash"])
            unique_missing_chunks.append(mc)

    log(f"Missing WAV chunks: {len(unique_missing_chunks)} (unique) / {len(missing_chunks)} (total)")

    # Synthesize missing chunks if any
    if unique_missing_chunks:
        # Acquire termux-wake-lock
        try:
            log("Acquiring termux-wake-lock...")
            subprocess.run(["termux-wake-lock"], check=False)
        except Exception as e:
            log(f"Warning: termux-wake-lock failed: {e}")

        try:
            # Prepare payload for piper_helper.py
            payload = {
                "model_path": model_path,
                "output_dir": os.path.abspath(chunks_dir),
                "chunks": unique_missing_chunks,
                "speaker_id": speaker_id,
                "speed": speed,
                "noise_scale": noise_scale,
                "noise_w": noise_w
            }
            payload_json = json.dumps(payload, ensure_ascii=False)

            # Call piper_helper.py inside the Ubuntu container via proot-distro
            helper_path = "/data/data/com.termux/files/home/kindle-butch-gen/bin/piper_helper.py"
            cmd = [
                "proot-distro", "login", "ubuntu", "--",
                "python3", helper_path
            ]
            
            log(f"Invoking piper_helper.py inside Ubuntu container using model: {model_path}...")
            subprocess.run(
                cmd,
                input=payload_json,
                text=True,
                check=True
            )

        except subprocess.CalledProcessError as e:
            log(f"Error: piper_helper.py failed with exit code {e.returncode}")
            sys.exit(1)
        except Exception as e:
            log(f"Error calling piper_helper.py: {e}")
            sys.exit(1)
        finally:
            # Release termux-wake-unlock
            try:
                log("Releasing termux-wake-unlock...")
                subprocess.run(["termux-wake-unlock"], check=False)
            except Exception as e:
                log(f"Warning: termux-wake-unlock failed: {e}")

        # Update cache for successfully synthesized files
        for chunk in unique_missing_chunks:
            h = chunk["hash"]
            t = chunk["text"]
            wav_file = os.path.join(chunks_dir, f"{h}.wav")
            if os.path.exists(wav_file):
                cache[h] = t

        # Save cache
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            log("Saved updated TTS cache.")
        except Exception as e:
            log(f"Warning: Failed to save TTS cache: {e}")

    # Verify all chunk files exist before proceeding
    missing_files = []
    for h in chunk_hashes:
        wav_file = os.path.join(chunks_dir, f"{h}.wav")
        if not os.path.exists(wav_file):
            missing_files.append(wav_file)

    if missing_files:
        log(f"Error: {len(missing_files)} chunk WAV files are missing even after synthesis. Aborting concatenation.")
        for mf in missing_files[:5]:
            log(f"  Missing: {mf}")
        sys.exit(1)

    log("All chunk files verified successfully.")

    # Create ffmpeg list file
    ffmpeg_list_path = os.path.join(paths["audio_dir"], "ffmpeg_list.txt")
    try:
        with open(ffmpeg_list_path, "w", encoding="utf-8") as lf:
            for h in chunk_hashes:
                chunk_file = os.path.abspath(os.path.join(chunks_dir, f"{h}.wav"))
                escaped_path = chunk_file.replace("'", "'\\''")
                lf.write(f"file '{escaped_path}'\n")
    except Exception as e:
        log(f"Error writing ffmpeg list file: {e}")
        sys.exit(1)

    # Concatenate and encode to MP3
    output_mp3 = os.path.join(output_dir, f"{slug}_translated_{target_lang}.mp3")
    log(f"Concatenating chunks and encoding to: {output_mp3}")

    cmd_ffmpeg = [
        "proot-distro", "login", "ubuntu", "--",
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", os.path.abspath(ffmpeg_list_path),
        "-c:a", "libmp3lame", "-q:a", "4",
        os.path.abspath(output_mp3)
    ]

    try:
        subprocess.run(
            cmd_ffmpeg,
            check=True
        )
    except subprocess.CalledProcessError as e:
        log(f"Error: ffmpeg compilation/concatenation failed with exit code {e.returncode}")
        sys.exit(1)
    finally:
        # Clean up temporary ffmpeg list file
        if os.path.exists(ffmpeg_list_path):
            try:
                os.remove(ffmpeg_list_path)
            except Exception as e:
                log(f"Warning: Failed to remove temporary ffmpeg list file: {e}")

    log(f"Audiobook generation completed successfully! Saved to: {output_mp3}")

if __name__ == "__main__":
    main()
