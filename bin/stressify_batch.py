#!/usr/bin/env python3
import sys
import os
import json
import unicodedata

def normalize_accents(text):
    # Convert spacing acute accent (´, \u00b4) to combining acute accent (́, \u0301)
    return text.replace("\u00b4", "\u0301")

def main():
    input_path = "/data/data/com.termux/files/home/kindle-butch-gen/books/temp_unstressed.json"
    output_path = "/data/data/com.termux/files/home/kindle-butch-gen/books/temp_stressed.json"

    if not os.path.exists(input_path):
        print(f"[StressifyBatch] Error: Input file {input_path} not found.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[StressifyBatch] Error: Failed to parse input JSON: {e}", file=sys.stderr)
        sys.exit(1)

    chunks = data.get("chunks", [])
    lang = data.get("lang", "uk")

    stressifier = None
    if lang == "uk":
        try:
            from ukrainian_word_stress import Stressifier
            stressifier = Stressifier()
            print("[StressifyBatch] Initialized Stressifier successfully.", flush=True)
        except Exception as e:
            print(f"[StressifyBatch] Warning: Failed to load Stressifier: {e}. Stress will not be added.", file=sys.stderr)

    total = len(chunks)
    print(f"[StressifyBatch] Stressifying and normalizing {total} chunks...", flush=True)

    stressed_chunks = []
    for i, chunk in enumerate(chunks):
        h = chunk.get("hash")
        text = chunk.get("text", "")

        # 1. Add word stress if Ukrainian
        if lang == "uk" and stressifier is not None:
            try:
                stressed_text = stressifier(text)
            except Exception as e:
                # Fallback to raw text if stressifier fails on this chunk
                stressed_text = text
        else:
            stressed_text = text

        # 2. Normalize accent characters
        stressed_text = normalize_accents(stressed_text)

        # 3. Apply NFD Normalization (decomposes й -> и + Combining Breve, ї -> і + Combining Diaeresis)
        nfd_text = unicodedata.normalize("NFD", stressed_text)

        stressed_chunks.append({
            "hash": h,
            "text": nfd_text
        })

    # Save output
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"chunks": stressed_chunks}, f, ensure_ascii=False, indent=2)
        print("[StressifyBatch] Batch completed successfully.", flush=True)
    except Exception as e:
        print(f"[StressifyBatch] Error: Failed to save output JSON: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
