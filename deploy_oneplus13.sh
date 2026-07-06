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

log "Starting deployment of kindle-butch-gen on OnePlus 13..."

# -------------------------------------------------------------
# STEP 1: Install Termux Host Prerequisites
# -------------------------------------------------------------
log "Installing host Termux packages..."
pkg update -y
pkg install -y proot-distro git termux-exec clang cmake make ocl-icd opencl-headers rsync termux-api ffmpeg
success "Termux host packages installed."

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

# Create a launcher script to run Ubuntu with Adreno OpenCL GPU access
LAUNCHER_PATH="$HOME/ubuntu-gpu.sh"
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
chmod +x "$LAUNCHER_PATH"
success "GPU-enabled Ubuntu launcher created at ${LAUNCHER_PATH}."

# -------------------------------------------------------------
# STEP 3: Setup OpenCL ICD and Compile llama.cpp inside Ubuntu
# -------------------------------------------------------------
log "Configuring OpenCL and compiling llama.cpp inside Ubuntu container..."

# We write a setup script that will be executed inside the Ubuntu container
UBUNTU_SETUP_SCRIPT="/tmp/ubuntu_setup.sh"
cat << 'EOF' > "/data/data/com.termux/files/home/kindle-butch-gen/ubuntu_setup.sh"
#!/usr/bin/env bash
set -euo pipefail

echo "=== [Ubuntu Setup] ==="
apt update
apt install -y build-essential cmake git opencl-headers ocl-icd-opencl-dev clinfo python3-pip python3-venv libgomp1 calibre ffmpeg

# 1. Configure OpenCL ICD for Qualcomm Adreno GPU
echo "Configuring Adreno GPU OpenCL drivers..."
mkdir -p /etc/OpenCL/vendors
# Adreno driver on Android is traditionally located in /vendor/lib64/libOpenCL.so
# KGSL (/dev/kgsl) device permissions are required to access GPU hardware
echo "/vendor/lib64/libOpenCL.so" > /etc/OpenCL/vendors/adreno.icd

# Run clinfo to verify OpenCL is active and recognizes the Adreno GPU
echo "Verifying OpenCL devices..."
if clinfo | grep -q -i "platform"; then
    echo "OpenCL platform verified successfully:"
    clinfo | grep -E -i "Name|Vendor|Version"
else
    echo "Warning: clinfo failed to list OpenCL devices. GPU acceleration might not be fully working yet."
fi

# 2. Compile llama.cpp with native OpenCL acceleration (highly optimized for Adreno)
echo "Cloning and building llama.cpp with native OpenCL..."
cd /tmp
if [ -d "llama.cpp" ]; then rm -rf llama.cpp; fi
git clone --depth 1 https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
mkdir build && cd build
cmake .. -DGGML_OPENCL=ON
make -j$(nproc)

# Copy compiled binaries to system path
cp bin/llama-cli bin/llama-server /usr/local/bin/
echo "llama.cpp compiled and installed to /usr/local/bin/."

# 3. Setup Python Virtual Environment for OCR (Marker) and PyTorch
echo "Setting up Python virtual environment for OCR..."
cd /home/vokov || mkdir -p /home/vokov && cd /home/vokov
python3 -m venv venv-ocr
source venv-ocr/bin/activate
pip install --upgrade pip
# Install PyTorch (CPU version is optimized with OpenMP on Snapdragon ARM64)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install marker-pdf pydantic transformers

echo "=== [Ubuntu Setup Completed] ==="
EOF

# Move setup script into the PRoot container space and run it
log "Copying setup script to Ubuntu container and running it..."
"$LAUNCHER_PATH" -- bash -c "cat /data/data/com.termux/files/home/kindle-butch-gen/ubuntu_setup.sh > /tmp/setup.sh && chmod +x /tmp/setup.sh && /tmp/setup.sh"
rm -f /data/data/com.termux/files/home/kindle-butch-gen/ubuntu_setup.sh

success "Ubuntu compilation and setup finished successfully."

# -------------------------------------------------------------
# STEP 4: Setup local kindle-butch-gen project copy
# -------------------------------------------------------------
log "Setting up kindle-butch-gen files..."
mkdir -p "$HOME/kindle-butch-gen"
# Run verification check
chmod +x "$HOME/kindle-butch-gen/kbg.sh" || true

log "Deployment complete!"
echo -e "\n${GREEN}===================================================================${NC}"
echo -e " kindle-butch-gen is deployed on your OnePlus 13!"
echo -e " To enter the GPU-enabled Ubuntu environment, run:"
echo -e "   👉 ${LAUNCHER_PATH}"
echo -e " To test Adreno OpenCL acceleration, run inside Ubuntu:"
echo -e "   👉 clinfo"
echo -e " To run translation server accelerated by Adreno GPU, run:"
echo -e "   👉 llama-server -m <model_path> -c 2048 --port 8081 -ngl 99"
echo -e "${GREEN}===================================================================${NC}\n"
