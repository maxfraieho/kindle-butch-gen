#!/usr/bin/env python3
import sys
import os
import json
import re
import subprocess
from ukrainian_word_stress import Stressifier

vowels = "аеиоуіяеїєюАЕИОУІЯЕЇЄЮ"

def normalize_accents(text):
    # Convert spacing acute accent (´, \u00b4) to combining acute accent (́, \u0301)
    return text.replace("\u00b4", "\u0301")

def main():
    # Read JSON payload from stdin
    try:
        payload = json.load(sys.stdin)
    except Exception as e:
        print(f"[PiperHelper] Error: Failed to parse JSON from stdin: {e}", file=sys.stderr)
        sys.exit(1)

    model_path = payload.get("model_path")
    output_dir = payload.get("output_dir")
    chunks = payload.get("chunks", [])
    speaker_id = payload.get("speaker_id", 2)
    speed = payload.get("speed", 1.0)
    noise_scale = payload.get("noise_scale", 0.667)
    noise_w = payload.get("noise_w", 0.8)
    lang = payload.get("lang", "uk")
    length_scale = 1.0 / speed

    if not model_path or not output_dir:
        print("[PiperHelper] Error: model_path and output_dir are required in payload", file=sys.stderr)
        sys.exit(1)

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Initialize Stressifier once (only for Ukrainian)
    stressifier = None
    if lang == "uk":
        try:
            stressifier = Stressifier()
        except Exception as e:
            print(f"[PiperHelper] Error: Failed to initialize Stressifier: {e}", file=sys.stderr)
            sys.exit(1)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    piper_binary = os.path.join(script_dir, "piper", "piper")
    piper_lib_path = os.path.join(script_dir, "piper")

    # Set up environment for subprocess
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = piper_lib_path

    total = len(chunks)
    print(f"[PiperHelper] Processing {total} chunks using model {model_path}...", flush=True)

    for i, chunk in enumerate(chunks):
        chunk_hash = chunk.get("hash")
        text = chunk.get("text", "").strip()

        if not chunk_hash or not text:
            print(f"[PiperHelper] Warning: Skipping chunk {i+1} due to missing hash or text", file=sys.stderr)
            continue

        # 1. Apply stressify to the text if lang == "uk"
        if lang == "uk" and stressifier is not None:
            try:
                stressed_text = stressifier(text)
            except Exception as e:
                print(f"[PiperHelper] Warning: Stressifier failed on chunk {chunk_hash}: {e}. Using raw text.", file=sys.stderr)
                stressed_text = text
        else:
            stressed_text = text

        # 2. Normalize acute accent U+00B4 to combining acute accent U+0301
        stressed_text_normalized = normalize_accents(stressed_text)

        # Output wav file path
        output_file = os.path.join(output_dir, f"{chunk_hash}.wav")

        # Explicitly print the text and model path for first 5 chunks for E2E validation
        if i < 5:
            print(f"[PiperHelper] [{i+1}/{total}] Synthesizing chunk {chunk_hash}:", flush=True)
            print(f"  - Voice Model: {model_path}", flush=True)
            print(f"  - Cleaned text: '{text}'", flush=True)
            print(f"  - Stressed text: '{stressed_text_normalized}'", flush=True)
        else:
            print(f"[PiperHelper] [{i+1}/{total}] Synthesizing chunk {chunk_hash}...", flush=True)

        # 3. Run piper C++ binary using subprocess
        # Pass the stressed text to piper's stdin
        # Command arguments: -m <model_path> -f <output_file>
        cmd = [
            piper_binary,
            "-m", model_path,
            "-s", str(speaker_id),
            "--length_scale", str(length_scale),
            "--noise_scale", str(noise_scale),
            "--noise_w", str(noise_w),
            "-f", output_file
        ]

        try:
            # We run subprocess.run, passing stressed_text_normalized as stdin input.
            res = subprocess.run(
                cmd,
                input=stressed_text_normalized,
                capture_output=True,
                text=True,
                env=env,
                check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"[PiperHelper] Error: Piper failed on chunk {chunk_hash} with exit code {e.returncode}.", file=sys.stderr)
            if e.stdout:
                print(f"[PiperHelper] Piper stdout:\n{e.stdout}", file=sys.stderr)
            if e.stderr:
                print(f"[PiperHelper] Piper stderr:\n{e.stderr}", file=sys.stderr)
            # We don't crash the whole batch, but we notify the user.
        except Exception as e:
            print(f"[PiperHelper] Error: Unexpected error running Piper on chunk {chunk_hash}: {e}", file=sys.stderr)

    print("[PiperHelper] Done processing chunks.", flush=True)

if __name__ == "__main__":
    main()
