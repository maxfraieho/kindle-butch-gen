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

def run_piper(payload):
    from ukrainian_word_stress import Stressifier

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
        print("[TTSHelper] Error: model_path and output_dir are required for Piper", file=sys.stderr)
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    stressifier = None
    if lang == "uk":
        try:
            stressifier = Stressifier()
        except Exception as e:
            print(f"[TTSHelper] Error: Failed to initialize Stressifier: {e}", file=sys.stderr)
            sys.exit(1)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    # piper binary is in the same directory as script (bin/piper/piper)
    piper_binary = os.path.join(script_dir, "piper", "piper")
    piper_lib_path = os.path.join(script_dir, "piper")

    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = piper_lib_path

    total = len(chunks)
    print(f"[TTSHelper] (Piper) Processing {total} chunks using model {model_path}...", flush=True)

    for i, chunk in enumerate(chunks):
        chunk_hash = chunk.get("hash")
        text = chunk.get("text", "").strip()

        if not chunk_hash or not text:
            continue

        if lang == "uk" and stressifier is not None:
            try:
                stressed_text = stressifier(text)
            except Exception as e:
                print(f"[TTSHelper] Warning: Stressifier failed on chunk {chunk_hash}: {e}. Using raw text.", file=sys.stderr)
                stressed_text = text
        else:
            stressed_text = text

        stressed_text_normalized = normalize_accents(stressed_text)
        output_file = os.path.join(output_dir, f"{chunk_hash}.wav")

        if i < 5:
            print(f"[TTSHelper] [{i+1}/{total}] Synthesizing chunk {chunk_hash}:", flush=True)
            print(f"  - Voice Model: {model_path}", flush=True)
            print(f"  - Cleaned text: '{text}'", flush=True)
            print(f"  - Stressed text: '{stressed_text_normalized}'", flush=True)
        else:
            print(f"[TTSHelper] [{i+1}/{total}] Synthesizing chunk {chunk_hash}...", flush=True)

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
            subprocess.run(
                cmd,
                input=stressed_text_normalized,
                capture_output=True,
                text=True,
                env=env,
                check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"[TTSHelper] Error: Piper failed on chunk {chunk_hash} with exit code {e.returncode}.", file=sys.stderr)
            if e.stdout:
                print(f"[TTSHelper] Piper stdout:\n{e.stdout}", file=sys.stderr)
            if e.stderr:
                print(f"[TTSHelper] Piper stderr:\n{e.stderr}", file=sys.stderr)
        except Exception as e:
            print(f"[TTSHelper] Error: Unexpected error running Piper on chunk {chunk_hash}: {e}", file=sys.stderr)

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

    engine = payload.get("tts_engine", "piper")
    if engine == "piper":
        run_piper(payload)
    elif engine == "supertonic3":
        run_supertonic3(payload)
    else:
        print(f"[TTSHelper] Error: Unsupported tts_engine '{engine}'", file=sys.stderr)
        sys.exit(1)

    print("[TTSHelper] Done processing chunks.", flush=True)

if __name__ == "__main__":
    main()
