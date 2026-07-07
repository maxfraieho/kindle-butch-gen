#!/usr/bin/env python3
import sys
import os
import json
import re
import subprocess
import wave
import struct

def normalize_accents(text):
    # Convert spacing acute accent (´, \u00b4) to combining acute accent (́, \u0301)
    return text.replace("\u00b4", "\u0301")



def run_supertonic3(payload):
    import sherpa_onnx

    output_dir = payload.get("output_dir")
    chunks = payload.get("chunks", [])
    speaker_id = payload.get("speaker_id", 2)
    speed = payload.get("speed", 1.0)
    lang = payload.get("lang", "uk")

    if not output_dir:
        print("[TTSHelper] Error: output_dir is required for Supertonic 3", file=sys.stderr)
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    # Resolve model directory (default inside kindle-butch-gen/models)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = os.path.abspath(os.path.join(script_dir, ".."))
    model_dir = os.path.join(repo_dir, "models", "sherpa-onnx-supertonic-3-tts-int8-2026-05-11")

    if not os.path.exists(model_dir):
        print(f"[TTSHelper] Error: Supertonic 3 model directory not found at {model_dir}", file=sys.stderr)
        sys.exit(1)

    # Initialize OfflineTts
    tts_config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            supertonic=sherpa_onnx.OfflineTtsSupertonicModelConfig(
                duration_predictor=os.path.join(model_dir, "duration_predictor.int8.onnx"),
                text_encoder=os.path.join(model_dir, "text_encoder.int8.onnx"),
                vector_estimator=os.path.join(model_dir, "vector_estimator.int8.onnx"),
                vocoder=os.path.join(model_dir, "vocoder.int8.onnx"),
                tts_json=os.path.join(model_dir, "tts.json"),
                unicode_indexer=os.path.join(model_dir, "unicode_indexer.bin"),
                voice_style=os.path.join(model_dir, "voice.bin"),
            ),
            debug=False,
            num_threads=4,
            provider="nnapi",
        )
    )

    if not tts_config.validate():
        print("[TTSHelper] Error: Supertonic 3 configuration validation failed", file=sys.stderr)
        sys.exit(1)

    tts = sherpa_onnx.OfflineTts(tts_config)

    gen_config = sherpa_onnx.GenerationConfig()
    gen_config.sid = int(speaker_id)
    gen_config.num_steps = 5
    gen_config.speed = float(speed)
    gen_config.extra["lang"] = lang

    # Load cache dynamically
    cache_path = os.path.join(os.path.dirname(output_dir), "tts_cache_supertonic-3-tts-int8.json")
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            pass

    total = len(chunks)
    print(f"[TTSHelper] (Supertonic 3) Processing {total} chunks...", flush=True)

    for i, chunk in enumerate(chunks):
        chunk_hash = chunk.get("hash")
        text = chunk.get("text", "").strip()

        if not chunk_hash or not text:
            continue

        import unicodedata
        text = unicodedata.normalize("NFD", text)

        output_file = os.path.join(output_dir, f"{chunk_hash}.wav")

        if i < 5:
            print(f"[TTSHelper] [{i+1}/{total}] Synthesizing chunk {chunk_hash}:", flush=True)
            print(f"  - Cleaned text: '{text}'", flush=True)
        else:
            print(f"[TTSHelper] [{i+1}/{total}] Synthesizing chunk {chunk_hash}...", flush=True)

        try:
            audio = tts.generate(text, gen_config)
            if len(audio.samples) == 0:
                print(f"[TTSHelper] Error: Generated audio samples are empty for chunk {chunk_hash}", file=sys.stderr)
                continue

            # Decimate samples by 2 to downsample from 44100 Hz to 22050 Hz
            output_sample_rate = audio.sample_rate // 2
            int16_samples = [int(max(-1.0, min(1.0, s)) * 32767) for s in audio.samples[::2]]

            # Save wav file
            with wave.open(output_file, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(output_sample_rate)
                packed_data = struct.pack(f"{len(int16_samples)}h", *int16_samples)
                wav_file.writeframes(packed_data)

            # Update cache file dynamically
            cache[chunk_hash] = text
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        except Exception as e:
            print(f"[TTSHelper] Error running Supertonic 3 on chunk {chunk_hash}: {e}", file=sys.stderr)

def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as e:
        print(f"[TTSHelper] Error: Failed to parse JSON from stdin: {e}", file=sys.stderr)
        sys.exit(1)

    engine = payload.get("tts_engine", "supertonic3")
    if engine == "supertonic3":
        run_supertonic3(payload)
    else:
        print(f"[TTSHelper] Error: Unsupported tts_engine '{engine}'", file=sys.stderr)
        sys.exit(1)

    print("[TTSHelper] Done processing chunks.", flush=True)

if __name__ == "__main__":
    main()
