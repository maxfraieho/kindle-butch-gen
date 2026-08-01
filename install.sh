#!/data/data/com.termux/files/usr/bin/bash
# Master Installer & Model Downloader for kindle-butch-gen (Vydra Studio)
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Vydra Studio (kindle-butch-gen) Setup & Model Download ==="

# 1. Install / Download Models
echo "[1/3] Завантаження нейромережевих моделей (StyleTTS2, Gemma 3 4B, Whisper ASR)..."
export CONSENT_ACCEPTED=1
bash "$SCRIPT_DIR/bin/download_premium_models.sh" --all

# 2. Build Frontend
if [ -d "$SCRIPT_DIR/frontend" ]; then
    echo "[2/3] Збірка фронтенду (Vite React)..."
    cd "$SCRIPT_DIR/frontend"
    npm install --silent || true
    npm run build
fi

# 3. Verify Models
echo "[3/3] Перевірка моделей..."
STYLETTS2_DIR="$HOME/kindle-butch-gen/models/styletts2"
if [ -f "$STYLETTS2_DIR/model.onnx" ] && [ -f "$STYLETTS2_DIR/style.npy" ]; then
    echo "  ✅ StyleTTS2: готові model.onnx та style.npy"
else
    echo "  ⚠️ StyleTTS2: не всі файли на місці!"
fi

echo "=== Встановлення успішно завершено! ==="
