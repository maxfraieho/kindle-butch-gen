#!/data/data/com.termux/files/usr/bin/bash
# Premium vision-model download (TASK-65 onboarding): Gemma 3 4B Q4_K_M
# (~2.5GB) + its vision projector (~850MB) from the official ggml-org
# GGUF repo. curl -C - makes re-runs resume instead of restarting, so a
# dropped mobile connection just needs another tap on the same button.
set -uo pipefail

MODEL_DIR="$HOME/models/gemma3-4b"
BASE_URL="https://huggingface.co/ggml-org/gemma-3-4b-it-GGUF/resolve/main"
mkdir -p "$MODEL_DIR"

echo "[premium-models] Starting download to $MODEL_DIR"
for f in gemma-3-4b-it-Q4_K_M.gguf mmproj-model-f16.gguf; do
    echo "[premium-models] Fetching $f..."
    curl -L -C - --fail --retry 3 -o "$MODEL_DIR/$f.part" "$BASE_URL/$f" \
        && mv "$MODEL_DIR/$f.part" "$MODEL_DIR/$f" \
        && echo "[premium-models] $f DONE" \
        || { echo "[premium-models] $f FAILED - re-run to resume"; exit 1; }
done
echo "[premium-models] All models ready."
