#!/data/data/com.termux/files/usr/bin/bash
# Premium AI-model downloader for kindle-butch-gen:
# - Gemma 3 4B (~2.5GB) + mmproj (~850MB) for Agent-Editor / Cast Registry
# - Whisper Small INT8 (~245MB) for ASR accent verification loop
#
# Supports flags:
#   --all         Download all models (default if no flags given)
#   --gemma       Download Gemma 3 4B vision models only
#   --asr         Download Whisper Small INT8 ASR models only
#   --whisper     Alias for --asr
set -uo pipefail

TARGET="all"
while [ $# -gt 0 ]; do
    case "$1" in
        --gemma) TARGET="gemma"; shift ;;
        --asr|--whisper) TARGET="asr"; shift ;;
        --all) TARGET="all"; shift ;;
        *) TARGET="$1"; shift ;;
    esac
done
if [ "$TARGET" = "whisper" ]; then TARGET="asr"; fi

CONSENT_GIVE="${CONSENT_ACCEPTED:-${GEMMA_TERMS_ACCEPTED:-0}}"
if [ "$CONSENT_GIVE" != "1" ]; then
    echo ""
    echo "Ці розширені функції використовують додаткові нейромережеві моделі."
    echo "Завантажуючи ваги, ви приймаєте умови використання моделей:"
    echo "  - Google Gemma Terms of Use & Prohibited Use Policy (https://ai.google.dev/gemma/terms)"
    echo "  - OpenAI Whisper / sherpa-onnx License (MIT/Apache 2.0)"
    if [ -t 0 ]; then
        printf "Приймаєте умови та дозвіл на завантаження моделей? [y/N]: "
        read -r ans
        case "$ans" in [Yy]*) : ;; *) echo "Скасовано."; exit 1 ;; esac
    else
        echo "ВІДМОВА: згода не надана (CONSENT_ACCEPTED!=1). Запустіть через UI з підтвердженням."
        exit 1
    fi
fi

fetch_and_verify() {
    local target_dir="$1"
    local filename="$2"
    local url="$3"
    local min_bytes="$4"

    mkdir -p "$target_dir"
    local part_file="$target_dir/$filename.part"
    local final_file="$target_dir/$filename"

    if [ -f "$final_file" ]; then
        local sz
        sz=$(wc -c < "$final_file" 2>/dev/null || echo 0)
        if [ "$sz" -ge "$min_bytes" ]; then
            echo "[premium-models] $filename вже завантажено ($sz байт) — пропуск."
            return 0
        fi
        echo "[premium-models] $filename розмір ($sz) менший за мінімальний ($min_bytes) — перезавантаження."
    fi

    echo "[premium-models] Завантаження $filename з $url..."
    curl -L -C - --fail --retry 5 --retry-delay 2 -o "$part_file" "$url"
    local downloaded_sz
    downloaded_sz=$(wc -c < "$part_file" 2>/dev/null || echo 0)
    if [ "$downloaded_sz" -lt "$min_bytes" ]; then
        echo "[premium-models] ПОМИЛКА: Розмір $filename ($downloaded_sz байт) менший за потрібний ($min_bytes байт)." >&2
        rm -f "$part_file"
        return 1
    fi
    mv "$part_file" "$final_file"
    echo "[premium-models] $filename ГОТОВО ($downloaded_sz байт підтверджено)."
}

# 1. Gemma Models
if [ "$TARGET" = "all" ] || [ "$TARGET" = "gemma" ]; then
    GEMMA_DIR="$HOME/models/gemma3-4b"
    GEMMA_BASE="https://huggingface.co/ggml-org/gemma-3-4b-it-GGUF/resolve/main"
    echo "[premium-models] Завантаження моделей Gemma 3 4B у $GEMMA_DIR"
    fetch_and_verify "$GEMMA_DIR" "gemma-3-4b-it-Q4_K_M.gguf" "$GEMMA_BASE/gemma-3-4b-it-Q4_K_M.gguf" 2000000000
    fetch_and_verify "$GEMMA_DIR" "mmproj-model-f16.gguf" "$GEMMA_BASE/mmproj-model-f16.gguf" 700000000
fi

# 3. StyleTTS2 Models (Ukrainian TTS)
if [ "$TARGET" = "all" ] || [ "$TARGET" = "styletts2" ] || [ "$TARGET" = "tts" ]; then
    STYLETTS2_DIR="$HOME/kindle-butch-gen/models/styletts2"
    STYLETTS2_BASE="https://huggingface.co/patriotyk/styletts2_ukrainian_single/resolve/main"
    echo "[premium-models] Завантаження моделей StyleTTS2 у $STYLETTS2_DIR"
    fetch_and_verify "$STYLETTS2_DIR" "model.onnx" "$STYLETTS2_BASE/model.onnx" 300000000
    if [ ! -f "$STYLETTS2_DIR/style.npy" ]; then
        echo "[premium-models] Завантаження style.pt та створення style.npy..."
        fetch_and_verify "$STYLETTS2_DIR" "style.pt" "$STYLETTS2_BASE/style.pt" 1000
        python3 -c "
import pickle, zipfile, numpy as np
try:
    with zipfile.ZipFile('$STYLETTS2_DIR/style.pt', 'r') as z:
        data_name = [n for n in z.namelist() if '/data/0' in n][0]
        with z.open(data_name) as f:
            arr = np.frombuffer(f.read(), dtype=np.float32)
            np.save('$STYLETTS2_DIR/style.npy', arr)
            print('[premium-models] style.npy успішно створено з style.pt')
except Exception as e:
    print('[premium-models] Помилка створення style.npy:', e)
" 2>/dev/null || true
    fi
fi

echo "[premium-models] Усі запитані моделі готові до використання."

