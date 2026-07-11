#!/usr/bin/env python3
"""Quick test for Hy-MT2-7B translation quality via /completion endpoint."""
import requests, json, sys

BASE_URL = "http://localhost:8081"

def check_model():
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"Health: {r.status_code} {r.text[:100]}")
    except Exception as e:
        print(f"Health check failed: {e}")
        return False

    try:
        r = requests.get(f"{BASE_URL}/props", timeout=5)
        if r.status_code == 200:
            props = r.json()
            print(f"Model: {props.get('model_alias', props.get('model', 'unknown'))}")
    except Exception as e:
        print(f"Props failed: {e}")
    return True

def translate_hy_mt2(text, source_lang="Russian", target_lang="Ukrainian"):
    raw_prompt = (
        f"<|hy_begin\u2581of\u2581sentence|>"
        f"<|hy_User|>Translate the following text from {source_lang} to {target_lang}. "
        f"Output only the translation, no explanations:\n\n{text}<|hy_Assistant|>"
    )

    data = {
        "prompt": raw_prompt,
        "temperature": 0.1,
        "top_p": 0.95,
        "top_k": 20,
        "repetition_penalty": 1.05,
        "n_predict": 512,
        "stop": ["<|hy_User|>", "<|hy_begin\u2581of\u2581sentence|>", "<|endoftext|>"]
    }

    try:
        resp = requests.post(f"{BASE_URL}/completion", json=data, timeout=120)
        if resp.status_code != 200:
            print(f"Error: {resp.status_code} {resp.text[:300]}")
            return None
        result = resp.json()
        return result.get("content", "").strip()
    except Exception as e:
        print(f"Request failed: {e}")
        return None

# Test cases (RU -> UK for vibe-programming book)
test_cases = [
    "Вайб-программирование — это новый подход к разработке программного обеспечения с использованием искусственного интеллекта.",
    "Искусственный интеллект меняет способ написания кода, делая его более доступным для всех разработчиков.",
    "В эпоху ИИ программисты всё меньше пишут код вручную и всё больше описывают желаемый результат.",
]

print("=== Hy-MT2-7B Translation Test (RU → UK) ===\n")
if not check_model():
    print("Server not ready!")
    sys.exit(1)

print()
for i, text in enumerate(test_cases, 1):
    print(f"--- Test {i} ---")
    print(f"RU: {text}")
    result = translate_hy_mt2(text)
    print(f"UK: {result}")
    print()
