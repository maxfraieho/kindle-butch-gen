#!/usr/bin/env bash
# kindle-butch-gen OnePlus 13 (Adreno 830 GPU + OpenCL) Deploy Script
# Run this script inside standard Termux on the target OnePlus 13 device.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[DEPL]${NC} $1"
}

success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

AUTOSTART=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -a|--autostart)
            AUTOSTART=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [-a|--autostart]"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [-a|--autostart]"
            exit 1
            ;;
    esac
done

log "Starting deployment of kindle-butch-gen on OnePlus 13..."

# Ask interactively if not passed as CLI argument
if [ "$AUTOSTART" = "false" ]; then
    echo -n -e "${BLUE}[DEPL]${NC} Do you want to configure automatic startup of services (sshd, llama-server, web server) on Termux launch? (y/N): "
    read -r choice
    case "$choice" in 
        [yY]|[yY][eE][sS])
            AUTOSTART=true
            log "Autostart configuration enabled."
            ;;
        *)
            AUTOSTART=false
            log "Autostart configuration skipped."
            ;;
    esac
fi

# -------------------------------------------------------------
# TASK-32: hold a wake-lock for the WHOLE script, not just the
# autostart-block's future Flask launch. This deploy run includes a
# long GPU compile (llama.cpp) and multi-GB model downloads - without
# this, Android can suspend/kill the whole process if the screen locks
# mid-run (the exact failure mode observed repeatedly this session with
# the manga pipeline before it got the same fix). trap on EXIT/INT/TERM
# (not just normal completion) so a Ctrl+C or an early `set -e` exit
# still releases it - the device must never be left locked-from-sleep
# permanently because this script died partway through.
# -------------------------------------------------------------
log "Acquiring termux-wake-lock for the duration of deployment..."
termux-wake-lock 2>/dev/null || true
release_deploy_wake_lock() {
    log "Releasing termux-wake-lock..."
    termux-wake-unlock 2>/dev/null || true
}
trap release_deploy_wake_lock EXIT INT TERM

# -------------------------------------------------------------
# STEP 1: Install Termux Host Prerequisites
# -------------------------------------------------------------
log "Installing host Termux packages..."
pkg update -y
pkg install -y proot-distro git termux-exec clang cmake make ocl-icd opencl-headers rsync termux-api ffmpeg python python-pip
pip install --upgrade pip --break-system-packages || true
pip install Flask flask-httpauth requests ukrainian_word_stress ipa-uk tqdm marisa-trie blinker --break-system-packages
success "Termux host packages installed."

# -------------------------------------------------------------
# TASK-32: GPU/Adreno detection - Stage 1 (Termux-side, cheap file
# check, before any Adreno-specific step runs). clinfo doesn't exist
# yet at this point (Step 3 is what installs it inside the container),
# so it can't gate whether we even attempt Step 2/3's Adreno-specific
# work - this file check is the earliest signal available. This is the
# ONE deliberately-designed fallback in this script (everything else
# here is meant to hard-stop via `set -e` on failure) - not a general
# error-tolerance policy.
# -------------------------------------------------------------
ADRENO_DETECTED=false
if [ -e /vendor/lib64/libOpenCL.so ]; then
    ADRENO_DETECTED=true
    success "Adreno GPU detected (/vendor/lib64/libOpenCL.so present)."
else
    log "No Adreno /vendor/lib64/libOpenCL.so found on this device."
    echo -e "${BLUE}[DEPL]${NC} This device's Ubuntu PRoot GPU bind-mounts and OpenCL config are Adreno/OnePlus-13-specific and will be skipped; building llama.cpp CPU-only instead."
fi

# -------------------------------------------------------------
# STEP 2: Configure Ubuntu PRoot Container with GPU Bind Mounts
# -------------------------------------------------------------
log "Setting up Ubuntu PRoot container..."
if ! proot-distro list | grep -q "Installed: yes" | grep -q "ubuntu"; then
    log "Installing Ubuntu container via proot-distro..."
    proot-distro install ubuntu
else
    log "Ubuntu container is already installed."
fi

# Create a launcher script to run Ubuntu - Adreno-bound if detected,
# plain otherwise (TASK-32 Stage 1 detection above).
LAUNCHER_PATH="$HOME/ubuntu-gpu.sh"
if [ "$ADRENO_DETECTED" = "true" ]; then
    log "Creating GPU-enabled Ubuntu launcher at ${LAUNCHER_PATH}..."
    cat << 'EOF' > "$LAUNCHER_PATH"
#!/usr/bin/env bash
# Runs Ubuntu PRoot container with Android system vendor directories bind-mounted for OpenCL GPU access
proot-distro login ubuntu \
  --bind /vendor:/vendor \
  --bind /system:/system \
  --bind /vendor/lib64:/vendor/lib64 \
  --bind /system/lib64:/system/lib64 \
  --bind /dev/kgsl:/dev/kgsl \
  "$@"
EOF
else
    log "Creating plain (CPU-only) Ubuntu launcher at ${LAUNCHER_PATH}..."
    cat << 'EOF' > "$LAUNCHER_PATH"
#!/usr/bin/env bash
# No Adreno GPU detected on this device - plain Ubuntu PRoot login, no GPU bind-mounts.
proot-distro login ubuntu "$@"
EOF
fi
chmod +x "$LAUNCHER_PATH"
success "Ubuntu launcher created at ${LAUNCHER_PATH}."

# -------------------------------------------------------------
# STEP 3: Clone/update the kindle-butch-gen project itself
# -------------------------------------------------------------
# TASK-32: this MUST happen before Step 4 below - Step 4 writes a setup
# script into $HOME/kindle-butch-gen/, which requires the directory (and
# therefore a real clone) to already exist. The previous script's Step 4
# only did `mkdir -p` + a `chmod ... || true` of a file that may not
# exist - it silently relied on the project already having been placed
# there some other way, which is exactly the gap this fixes.
REPO_URL="https://github.com/maxfraieho/kindle-butch-gen.git"
PROJECT_DIR="$HOME/kindle-butch-gen"
log "Setting up kindle-butch-gen project files..."
if [ -d "$PROJECT_DIR/.git" ]; then
    log "kindle-butch-gen already cloned at ${PROJECT_DIR}, pulling latest..."
    git -C "$PROJECT_DIR" pull --ff-only
    success "kindle-butch-gen updated to latest."
else
    log "Cloning kindle-butch-gen into ${PROJECT_DIR}..."
    git clone "$REPO_URL" "$PROJECT_DIR"
    success "kindle-butch-gen cloned."
fi
chmod +x "$PROJECT_DIR/kbg.sh"

# -------------------------------------------------------------
# STEP 4: Setup OpenCL ICD and Compile llama.cpp inside Ubuntu
# -------------------------------------------------------------
log "Configuring OpenCL and compiling llama.cpp inside Ubuntu container..."

# We write a setup script that will be executed inside the Ubuntu
# container. TASK-32: ADRENO_DETECTED is written first as a plain
# (interpolated) line, since the rest of this heredoc is deliberately
# single-quoted 'EOF' to protect its own $(nproc)/etc. variables (meant
# to be evaluated INSIDE the container at run time, not by this outer
# Termux shell at write time).
UBUNTU_SETUP_SCRIPT_PATH="/data/data/com.termux/files/home/kindle-butch-gen/ubuntu_setup.sh"
{
    echo "#!/usr/bin/env bash"
    echo "set -euo pipefail"
    echo "ADRENO_DETECTED=$ADRENO_DETECTED"
    cat << 'EOF'

echo "=== [Ubuntu Setup] ==="
apt update
apt install -y build-essential cmake git opencl-headers ocl-icd-opencl-dev clinfo python3-pip python3-venv libgomp1 calibre ffmpeg tesseract-ocr unrar-free p7zip-full libfreetype6-dev wamerican

# 1. Configure OpenCL ICD for Qualcomm Adreno GPU - TASK-32 Stage 2: only
# attempted if Stage 1 (Termux-side /vendor/lib64/libOpenCL.so check,
# done before this script was even written) found a GPU. clinfo's own
# result further downgrades CMAKE_GPU_FLAGS to CPU-only even when Stage 1
# passed, covering "the file exists but runtime GPU access is actually
# broken/denied".
CMAKE_GPU_FLAGS=""
if [ "$ADRENO_DETECTED" = "true" ]; then
    echo "Configuring Adreno GPU OpenCL drivers..."
    mkdir -p /etc/OpenCL/vendors
    # Adreno driver on Android is traditionally located in /vendor/lib64/libOpenCL.so
    # KGSL (/dev/kgsl) device permissions are required to access GPU hardware
    echo "/vendor/lib64/libOpenCL.so" > /etc/OpenCL/vendors/adreno.icd

    echo "Verifying OpenCL devices..."
    if clinfo | grep -q -i "platform"; then
        echo "OpenCL platform verified successfully:"
        clinfo | grep -E -i "Name|Vendor|Version"
        CMAKE_GPU_FLAGS="-DGGML_OPENCL=ON -DGGML_OPENCL_USE_ADRENO_KERNELS=ON"
    else
        echo "Warning: clinfo failed to list OpenCL devices even though /vendor/lib64/libOpenCL.so was present - falling back to a CPU-only build."
    fi
else
    echo "Skipping Adreno OpenCL configuration (no GPU detected on this device) - building CPU-only."
fi

# 2. Compile llama.cpp - TASK-32: resumable. Checks the actual install
# destination (/usr/local/bin, persistent inside this PRoot container)
# rather than a /tmp build-directory marker (/tmp is wiped on Android
# reboot) before doing a full rm -rf + reclone + recompile. This also
# correctly handles a build killed mid-compile (nothing yet installed to
# /usr/local/bin => rebuild) vs. a genuinely completed prior run (skip).
if [ -x /usr/local/bin/llama-server ] && [ -x /usr/local/bin/llama-cli ]; then
    echo "llama.cpp binaries already present at /usr/local/bin - skipping recompilation."
else
    echo "Cloning and building llama.cpp (flags: ${CMAKE_GPU_FLAGS:-CPU-only})..."
    cd /tmp
    if [ -d "llama.cpp" ]; then rm -rf llama.cpp; fi
    git clone --depth 1 https://github.com/ggerganov/llama.cpp.git
    cd llama.cpp
    mkdir build && cd build
    cmake .. $CMAKE_GPU_FLAGS
    make -j$(nproc)
    cp bin/llama-cli bin/llama-server /usr/local/bin/
    echo "llama.cpp compiled and installed to /usr/local/bin/."
fi

# 3. Setup Python OCR, Manga translation, and ML dependencies (including stress-uk)
echo "Installing Python dependencies (PyTorch, Transformers, Marker, Manga-OCR, Mokuro, PyTesseract, stress-uk, num2words)..."
pip install --upgrade pip --break-system-packages || true
# Install PyTorch (CPU version is optimized with OpenMP on Snapdragon ARM64)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu --break-system-packages
pip install marker-pdf pydantic transformers manga-ocr mokuro pytesseract stress-uk num2words --break-system-packages

echo "=== [Ubuntu Setup Completed] ==="
EOF
} > "$UBUNTU_SETUP_SCRIPT_PATH"

# Move setup script into the PRoot container space and run it
log "Copying setup script to Ubuntu container and running it..."
"$LAUNCHER_PATH" -- bash -c "cat $UBUNTU_SETUP_SCRIPT_PATH > /tmp/setup.sh && chmod +x /tmp/setup.sh && /tmp/setup.sh"
rm -f "$UBUNTU_SETUP_SCRIPT_PATH"

success "Ubuntu compilation and setup finished successfully."

# -------------------------------------------------------------
# STEP 5: Configure Autostart (Optional)
# -------------------------------------------------------------
if [ "$AUTOSTART" = "true" ]; then
    log "Configuring autostart of services in ~/.bashrc..."
    
    # Define the autostart block
    AUTOSTART_BLOCK=$(cat << 'EOF'

# ── Autostart Services ──────────────────────────────────────────
# Prevent duplicate instances and run asynchronously

# 1. Autostart SSH daemon
if ! pgrep -x "sshd" >/dev/null; then
    sshd
fi

# 2. Autostart Llama Translation Server (Hy-MT2-7B on port 8081)
if ! pgrep -f "llama-server.*8081" >/dev/null; then
    echo "Autostart: Starting llama-server on port 8081..."
    nohup bash "$HOME/start-translation-server.sh" > "$HOME/llama-boot.log" 2>&1 &
fi

# 3. Autostart Flask Web Server (on port 5000)
if ! pgrep -f "python3 kbg_web/app.py" >/dev/null; then
    echo "Autostart: Starting Flask web server on port 5000..."
    termux-wake-lock 2>/dev/null || true
    (cd "$HOME/kindle-butch-gen" &&  nohup python3 kbg_web/app.py --port 5000 > "$HOME/kbg-flask.log" 2>&1 &)
fi
EOF
)

    BASHRC_FILE="$HOME/.bashrc"
    if [ -f "$BASHRC_FILE" ] && grep -q "Autostart: Starting Flask web server" "$BASHRC_FILE"; then
        log "Autostart is already configured in ~/.bashrc."
    else
        echo "$AUTOSTART_BLOCK" >> "$BASHRC_FILE"
        success "Autostart configured successfully in ~/.bashrc."
    fi
fi

# -------------------------------------------------------------
# STEP 6: Check and Download Required Models (Interactive & Verified)
# -------------------------------------------------------------
log "Checking required models for the translation and TTS pipeline..."

# Helper function to download file with resume and size checks
check_and_download() {
    local label="$1"
    local file_path="$2"
    local url="$3"
    local expected_size="$4"
    
    local dir_path=$(dirname "$file_path")
    mkdir -p "$dir_path"
    
    if [ -f "$file_path" ]; then
        local actual_size=$(stat -c%s "$file_path" 2>/dev/null || stat -f%z "$file_path" 2>/dev/null || echo 0)
        if [ "$actual_size" -eq "$expected_size" ]; then
            success "$label is already present and verified ($actual_size bytes)."
            return 0
        else
            log "$label file size mismatch (found $actual_size, expected $expected_size). Redownloading..."
        fi
    fi
    
    log "Downloading $label..."
    while true; do
        # Use curl -C - to resume, -L to follow redirects, --progress-bar for user-friendly output
        if curl -L -C - --progress-bar -o "$file_path" "$url"; then
            local actual_size=$(stat -c%s "$file_path" 2>/dev/null || stat -f%z "$file_path" 2>/dev/null || echo 0)
            if [ "$actual_size" -eq "$expected_size" ]; then
                success "$label downloaded and verified successfully ($actual_size bytes)."
                return 0
            else
                echo -e "${RED}[ERROR]${NC} Download of $label was incomplete (got $actual_size bytes, expected $expected_size)."
            fi
        else
            echo -e "${RED}[ERROR]${NC} curl command failed during download of $label."
        fi
        
        echo -n -e "${BLUE}[DEPL]${NC} Do you want to resume/retry the download? (Y/n): "
        read -r retry_choice
        case "$retry_choice" in
            [nN]|[nN][oO])
                log "Download aborted by user."
                return 1
                ;;
            *)
                log "Retrying/resuming download..."
                ;;
        esac
    done
}

# 1. Check/Download Translation Model (Hy-MT2-7B GGUF)
MODEL_DIR="$HOME/models/hy-mt2"
MODEL_PATH="$MODEL_DIR/Hy-MT2-7B-Q4_K_M.gguf"
HY_MT2_SIZE=4624650016
HY_MT2_URL="https://huggingface.co/mradermacher/Hy-MT2-7B-i1-GGUF/resolve/main/Hy-MT2-7B.i1-Q4_K_M.gguf"

if [ -f "$MODEL_PATH" ]; then
    # Double check size of existing GGUF model
    actual_gguf_size=$(stat -c%s "$MODEL_PATH" 2>/dev/null || stat -f%z "$MODEL_PATH" 2>/dev/null || echo 0)
    if [ "$actual_gguf_size" -eq "$HY_MT2_SIZE" ]; then
        success "Translation model Hy-MT2-7B-Q4_K_M.gguf is already present and verified."
    else
        log "Translation model file size mismatch. Redownload recommended."
        rm -f "$MODEL_PATH"
    fi
fi

if [ ! -f "$MODEL_PATH" ]; then
    echo -e "\n${BLUE}[DEPL]${NC} Translation model Hy-MT2-7B-Q4_K_M.gguf (4.4GB) is missing."
    echo "This model is required for translating book texts."
    echo "Please choose an option:"
    echo "  1) Download the default model from Hugging Face (~4.4GB)"
    echo "  2) Paste a custom download link"
    echo "  3) Skip downloading for now"
    echo -n -e "${BLUE}[DEPL]${NC} Enter choice [1-3]: "
    read -r model_choice
    
    case "$model_choice" in
        1)
            check_and_download "Hy-MT2-7B GGUF Model" "$MODEL_PATH" "$HY_MT2_URL" "$HY_MT2_SIZE"
            ;;
        2)
            echo -n -e "${BLUE}[DEPL]${NC} Please paste the direct download URL for the GGUF model: "
            read -r custom_url
            if [ -n "$custom_url" ]; then
                log "Downloading model from custom URL..."
                curl -L -C - --progress-bar -o "$MODEL_PATH" "$custom_url"
                success "Model downloaded and saved to $MODEL_PATH."
            else
                log "Custom URL was empty. Skipping model download."
            fi
            ;;
        *)
            log "Model download skipped. You will need to manually place the model at $MODEL_PATH."
            ;;
    esac
fi

# 2. Check/Download Supertonic 3 TTS Model
TTS_DIR="$HOME/kindle-butch-gen/models"
TTS_ARCHIVE="$TTS_DIR/sherpa-onnx-supertonic-3-tts-int8-2026-05-11.tar.bz2"
TTS_EXTRACTED_DIR="$TTS_DIR/sherpa-onnx-supertonic-3-tts-int8-2026-05-11"
TTS_SIZE=128774318
TTS_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/sherpa-onnx-supertonic-3-tts-int8-2026-05-11.tar.bz2"

if [ -d "$TTS_EXTRACTED_DIR" ] && [ -f "$TTS_EXTRACTED_DIR/vocoder.int8.onnx" ]; then
    success "Supertonic 3 TTS models are already present at $TTS_EXTRACTED_DIR."
else
    echo -e "\n${BLUE}[DEPL]${NC} Supertonic 3 TTS model directory is missing or incomplete."
    echo "This is the premium default TTS voice model required for audiobook synthesis."
    echo -n -e "${BLUE}[DEPL]${NC} Do you want to download and extract Supertonic 3 TTS model? (Y/n): "
    read -r tts_choice
    case "$tts_choice" in
        [nN]|[nN][oO])
            log "Supertonic 3 TTS model download skipped."
            ;;
        *)
            if check_and_download "Supertonic 3 TTS Archive" "$TTS_ARCHIVE" "$TTS_URL" "$TTS_SIZE"; then
                log "Extracting Supertonic 3 model archive..."
                tar -xf "$TTS_ARCHIVE" -C "$TTS_DIR"
                if [ -d "$TTS_EXTRACTED_DIR" ]; then
                    success "Supertonic 3 TTS models extracted successfully."
                    rm -f "$TTS_ARCHIVE"
                else
                    error "Extraction failed. Directory $TTS_EXTRACTED_DIR was not created."
                fi
            fi
            ;;
    esac
fi

log "Deployment complete!"
echo -e "\n${GREEN}===================================================================${NC}"
echo -e " kindle-butch-gen is deployed!"
if [ "$ADRENO_DETECTED" = "true" ]; then
    echo -e " To enter the GPU-enabled Ubuntu environment, run:"
    echo -e "   👉 ${LAUNCHER_PATH}"
    echo -e " To test Adreno OpenCL acceleration, run inside Ubuntu:"
    echo -e "   👉 clinfo"
    echo -e " To run translation server accelerated by Adreno GPU, run:"
    echo -e "   👉 llama-server -m <model_path> -c 2048 --port 8081 -ngl 99"
else
    echo -e " No Adreno GPU was detected - built CPU-only. To enter Ubuntu, run:"
    echo -e "   👉 ${LAUNCHER_PATH}"
    echo -e " To run the translation server (CPU-only), run:"
    echo -e "   👉 llama-server -m <model_path> -c 2048 --port 8081"
fi
echo -e ""
echo -e " TASK-32: this device isn't automatically tracked by GitNexus code"
echo -e " search (which runs on the LAN dev server, not this device). If it"
echo -e " should be, run this on the dev server (192.168.3.184):"
echo -e "   👉 docker exec gitnexus-server node /app/gitnexus/dist/cli/index.js analyze /projects/kindle-butch-gen"
echo -e "${GREEN}===================================================================${NC}\n"
