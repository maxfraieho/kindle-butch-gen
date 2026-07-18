#!/data/data/com.termux/files/usr/bin/bash
# Premium vision-model download (TASK-65 onboarding): Gemma 3 4B Q4_K_M
# (~2.5GB) + its vision projector (~850MB) from the official ggml-org
# GGUF repo. curl -C - makes re-runs resume instead of restarting, so a
# dropped mobile connection just needs another tap on the same button.
set -uo pipefail

MODEL_DIR="$HOME/models/gemma3-4b"
BASE_URL="https://huggingface.co/ggml-org/gemma-3-4b-it-GGUF/resolve/main"
mkdir -p "$MODEL_DIR"

# Gemma Terms of Use consent gate (legal hardening): the Gemma license
# requires the distributor to flow the Prohibited Use Policy down to end
# users before they obtain the weights. Accepted either via the UI
# onboarding dialog (which sets GEMMA_TERMS_ACCEPTED=1) or interactively
# here for a manual terminal run.
if [ "${GEMMA_TERMS_ACCEPTED:-}" != "1" ]; then
    echo ""
    echo "Ця преміум-функція використовує модель Google Gemma."
    echo "Завантажуючи ваги, ви приймаєте Gemma Terms of Use і Prohibited"
    echo "Use Policy (заборона генерації незаконного/шкідливого контенту):"
    echo "  https://ai.google.dev/gemma/terms"
    echo "  https://ai.google.dev/gemma/prohibited_use_policy"
    if [ -t 0 ]; then
        printf "Приймаєте умови? [y/N]: "
        read -r ans
        case "$ans" in [Yy]*) : ;; *) echo "Скасовано."; exit 1 ;; esac
    else
        echo "ВІДМОВА: згода не надана (GEMMA_TERMS_ACCEPTED!=1). Запустіть через UI."
        exit 1
    fi
fi

echo "[premium-models] Starting download to $MODEL_DIR"
for f in gemma-3-4b-it-Q4_K_M.gguf mmproj-model-f16.gguf; do
    echo "[premium-models] Fetching $f..."
    curl -L -C - --fail --retry 3 -o "$MODEL_DIR/$f.part" "$BASE_URL/$f" \
        && mv "$MODEL_DIR/$f.part" "$MODEL_DIR/$f" \
        && echo "[premium-models] $f DONE" \
        || { echo "[premium-models] $f FAILED - re-run to resume"; exit 1; }
done
echo "[premium-models] All models ready."
