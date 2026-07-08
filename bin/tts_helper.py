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
    gen_config.num_steps = 8
    gen_config.speed = float(speed)
    gen_config.extra["lang"] = lang

    # Load cache dynamically
    cache_path = payload.get("cache_path")
    if not cache_path:
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

def run_styletts2(payload):
    import onnxruntime
    import numpy as np
    from ipa_uk import ipa

    output_dir = payload.get("output_dir")
    chunks = payload.get("chunks", [])
    speed = float(payload.get("speed", 1.0))

    if not output_dir:
        print("[TTSHelper] Error: output_dir is required for StyleTTS2", file=sys.stderr)
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = os.path.abspath(os.path.join(script_dir, ".."))
    model_path = os.path.join(repo_dir, "models", "styletts2", "model.onnx")
    style_path = os.path.join(repo_dir, "models", "styletts2", "style.npy")

    if not os.path.exists(model_path) or not os.path.exists(style_path):
        print(f"[TTSHelper] Error: StyleTTS2 model files not found at {model_path} or {style_path}", file=sys.stderr)
        sys.exit(1)

    # Vocabulary for tokenization
    VOCAB = [
        '$', '-', '´', ';', ':', ',', '.', '!', '?', '¡', '¿', '—', '…', '"', '«', '»', '“', '”', ' ', 
        '(', ')', '†', '/', '=', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 
        'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 
        'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z', 
        'é', 'ý', 'í', 'ó', "'", '̯', "'", '͡', 'ɑ', 'ɐ', 'ɒ', 'æ', 'ɓ', 'ʙ', 'β', 'ɔ', 'ɕ', 'ç', 'ɗ', 
        'ɖ', 'ð', 'ʤ', 'ə', 'ɘ', 'ɚ', 'ɛ', 'ɜ', 'ɝ', 'ɞ', 'ɟ', 'ʄ', 'ɡ', 'ɠ', 'ɢ', 'ʛ', 'ɦ', 'ɧ', 'ħ', 
        'ɥ', 'ʜ', 'ɨ', 'ɪ', 'ʝ', 'ɭ', 'ɬ', 'ɫ', 'ɮ', 'ʟ', 'ɱ', 'ɯ', 'ɰ', 'ŋ', 'ɳ', 'ɲ', 'ɴ', 'ø', 'ɵ', 
        'ɸ', 'θ', 'œ', 'ɶ', 'ʘ', 'ɹ', 'ɺ', 'ɾ', 'ɻ', 'ʀ', 'ʁ', 'ɽ', 'ʂ', 'ʃ', 'ʈ', 'ʧ', 'ʉ', 'ʊ', 'ʋ', 
        'ⱱ', 'ʌ', 'ɣ', 'ɤ', 'ʍ', 'χ', 'ʎ', 'ʏ', 'ʑ', 'ʐ', 'ʒ', 'ʔ', 'ʡ', 'ʕ', 'ʢ', 'ǀ', 'ǁ', 'ǂ', 'ǃ', 
        'ˈ', 'ˌ', 'ː', 'ˑ', 'ʼ', 'ʴ', 'ʰ', 'ʱ', 'ʲ', "'", '̩', "'", 'ᵻ'
    ]
    vocab_dict = {char: idx for idx, char in enumerate(VOCAB)}

    # Initialize Session
    sess_options = onnxruntime.SessionOptions()
    sess = onnxruntime.InferenceSession(model_path, sess_options, providers=['NnapiExecutionProvider', 'CPUExecutionProvider'])
    s_prev = np.load(style_path).astype(np.float32)

    # Load cache dynamically
    cache_path = payload.get("cache_path")
    if not cache_path:
        cache_path = os.path.join(os.path.dirname(output_dir), "tts_cache_styletts2.json")
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            pass

    total = len(chunks)
    print(f"[TTSHelper] (StyleTTS2) Processing {total} chunks...", flush=True)

    for i, chunk in enumerate(chunks):
        chunk_hash = chunk.get("hash")
        text = chunk.get("text", "").strip()

        if not chunk_hash or not text:
            continue

        # Replace '+' with Combining Acute Accent for proper phonemization
        cleaned_text = text.replace('+', '\u0301')

        # Transcribe to IPA
        ipa_text = ipa(cleaned_text)
        
        # Tokenize
        indexes = []
        for char in ipa_text:
            if char in vocab_dict:
                indexes.append(vocab_dict[char])
        tokens = np.array(indexes, dtype=np.int64)

        output_file = os.path.join(output_dir, f"{chunk_hash}.wav")

        if i < 5:
            print(f"[TTSHelper] [{i+1}/{total}] Synthesizing chunk {chunk_hash}:", flush=True)
            print(f"  - Original: '{text}'", flush=True)
            print(f"  - IPA: '{ipa_text}'", flush=True)
        else:
            print(f"[TTSHelper] [{i+1}/{total}] Synthesizing chunk {chunk_hash}...", flush=True)

        try:
            inputs = {
                'tokens': tokens,
                'speed': np.array(speed, dtype=np.float32),
                's_prev': s_prev
            }
            outputs = sess.run(None, inputs)
            audio_samples = outputs[0]

            if len(audio_samples) == 0:
                print(f"[TTSHelper] Error: Generated audio samples are empty for chunk {chunk_hash}", file=sys.stderr)
                continue

            # Normalize samples to int16
            int16_samples = [int(max(-1.0, min(1.0, s)) * 32767) for s in audio_samples]

            # Save wav file (StyleTTS2 native sample rate is 24000 Hz)
            with wave.open(output_file, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(24000)
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
            print(f"[TTSHelper] Error running StyleTTS2 on chunk {chunk_hash}: {e}", file=sys.stderr)

def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as e:
        print(f"[TTSHelper] Error: Failed to parse JSON from stdin: {e}", file=sys.stderr)
        sys.exit(1)

    engine = payload.get("tts_engine", "supertonic3")
    if engine == "supertonic3":
        run_supertonic3(payload)
    elif engine == "styletts2":
        run_styletts2(payload)
    else:
        print(f"[TTSHelper] Error: Unsupported tts_engine '{engine}'", file=sys.stderr)
        sys.exit(1)

    print("[TTSHelper] Done processing chunks.", flush=True)

if __name__ == "__main__":
    main()
