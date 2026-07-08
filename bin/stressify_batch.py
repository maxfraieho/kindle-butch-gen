#!/usr/bin/env python3
import sys
import os
import json
import unicodedata

from ukrainian_word_stress.stressify_ import _parse_dictionary_value
import marisa_trie
import re

class FastStressifier:
    def __init__(self, stress_symbol="+"):
        try:
            import ukrainian_word_stress
            dict_path = os.path.join(os.path.dirname(ukrainian_word_stress.__file__), "data/stress.trie")
        except Exception:
            dict_path = "/usr/local/lib/python3.14/dist-packages/ukrainian_word_stress/data/stress.trie"
            
        self.dict = marisa_trie.BytesTrie()
        self.dict.load(dict_path)
        self.stress_symbol = stress_symbol

    def __call__(self, text):
        tokens = re.split(r'(\w+)', text)
        result = []
        for token in tokens:
            if not token.isalnum():
                result.append(token)
                continue
            
            # Count Ukrainian vowels to skip monosyllabic words
            vowels = re.findall(r'[аеєиіїоуюяАЕЄИІЇОУЮЯ]', token)
            if len(vowels) <= 1:
                result.append(token)
                continue
                
            accents = []
            for word in (token, token.lower(), token.title()):
                if word in self.dict:
                    values = self.dict[word]
                    accents_by_tags = _parse_dictionary_value(values[0])
                    if accents_by_tags:
                        accents = accents_by_tags[0][1]
                    break
            
            if accents:
                accented_word = token
                for position in sorted(accents, reverse=True):
                    accented_word = accented_word[:position] + self.stress_symbol + accented_word[position:]
                result.append(accented_word)
            else:
                result.append(token)
                
        return "".join(result)

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
            stressifier = FastStressifier(stress_symbol="+")
            print("[StressifyBatch] Initialized FastStressifier successfully.", flush=True)
        except Exception as e:
            print(f"[StressifyBatch] Warning: Failed to load FastStressifier: {e}. Stress will not be added.", file=sys.stderr)

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
                stressed_text = text
        else:
            stressed_text = text

        # 2. Normalize accent characters
        stressed_text = normalize_accents(stressed_text)

        # 3. Apply NFD Normalization
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
