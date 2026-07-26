#!/bin/bash
# ============================================================================
# install-alpine-arm64.sh — Vydra (kindle-butch-gen) installer for the
# native Alpine Linux terminal running inside Acode (Android code editor,
# terminal plugin), on ARM64 phones.
#
# TARGET ENVIRONMENT (confirmed with Q, 2026-07-26): a real Alpine rootfs
# (apk, musl, genuine Alpine userland) wrapped in a proot sandbox provided
# by Acode itself. This is NOT Termux — there is no `pkg`, no
# `proot-distro`, no `termux-wake-lock`/termux-api, no Android bionic libc.
#
# ARCHITECTURE (mirrors the existing Termux deploy.sh split):
#   - llama.cpp is compiled NATIVE on the Alpine host. musl handles C/C++
#     fine, and this is the fastest path to any Adreno OpenCL access.
#   - The heavy Python/ML stack (torch, marker-pdf, manga-ocr, mokuro,
#     calibre, tesseract) needs glibc manylinux wheels / apt packages that
#     do not exist for musl — so it runs inside a proot'd Ubuntu 24.04
#     rootfs, bootstrapped by hand here (Alpine has no proot-distro pkg).
#   - run_conversion_batches.py / translate_manga.py hardcode the literal
#     command `proot-distro login ubuntu -- <cmd>` for the marker-pdf and
#     calibre stages (Termux-only tool). Rather than patch shared app code,
#     this installer places a `proot-distro` SHIM on PATH (see
#     bin/proot-distro-shim.sh below) that emulates just that one
#     invocation against our manually-bootstrapped rootfs. This keeps the
#     script forward-compatible with `git pull` from the upstream repo.
#
# KNOWN UNTESTED RISK (flagged up front, not discovered mid-script): this
# nests a SECOND proot instance inside Acode's own proot session. Nested
# ptrace-based sandboxing can fail on some kernels/proot builds ("ptrace:
# Operation not permitted"). STEP 0b below runs a cheap nested-proot probe
# BEFORE any expensive download/compile, specifically so that failure is
# caught early with a clear message instead of after a 10-20 min build.
# ============================================================================

set -euo pipefail

# --- self-bootstrap into bash ----------------------------------------------
if [ -z "${BASH_VERSION:-}" ]; then
    if ! command -v bash >/dev/null 2>&1; then
        echo "[install] bash not found on PATH — installing via apk..."
        apk add --no-cache bash
    fi
    exec bash "$0" "$@"
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m'

log()     { echo -e "${BLUE}[VYDRA]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

HOME="${HOME:-/root}"
REPO_URL="https://github.com/maxfraieho/kindle-butch-gen.git"
PROJECT_DIR="$HOME/kindle-butch-gen"
ROOTFS_DIR="$HOME/ubuntu-rootfs"
LLAMA_DIR="$HOME/llama.cpp"
SHIM_DIR="$HOME/.local/bin"
UBUNTU_BASE_URL="https://cdimage.ubuntu.com/ubuntu-base/releases/24.04/release/ubuntu-base-24.04-base-arm64.tar.gz"

log "Vydra (kindle-butch-gen) — Alpine/Acode ARM64 installer"
log "HOME=$HOME  PROJECT_DIR=$PROJECT_DIR  ROOTFS_DIR=$ROOTFS_DIR"

# ---------------------------------------------------------------------------
# STEP 0: Pre-flight diagnostics — fail fast, before any long step.
# ---------------------------------------------------------------------------
log "Running pre-flight diagnostics..."
DIAG_FAILED=0
diag() { # $1=PASS|WARN|FAIL $2=label $3=detail
    case "$1" in
        PASS) echo -e "  ${GREEN}[PASS]${NC} $2 — $3" ;;
        WARN) echo -e "  ${YELLOW}[WARN]${NC} $2 — $3" ;;
        FAIL) echo -e "  ${RED}[FAIL]${NC} $2 — $3"; DIAG_FAILED=1 ;;
    esac
}

case "$(uname -m)" in
    aarch64) diag PASS "Архітектура" "aarch64" ;;
    *) diag FAIL "Архітектура" "$(uname -m) — цей скрипт для aarch64 (ARM64 телефон)" ;;
esac

if grep -qi '^ID=alpine' /etc/os-release 2>/dev/null; then
    diag PASS "ОС" "Alpine $(grep '^VERSION_ID=' /etc/os-release | cut -d= -f2)"
else
    diag FAIL "ОС" "/etc/os-release не показує Alpine — цей скрипт саме для Alpine (не Termux/Ubuntu)"
fi

command -v apk >/dev/null 2>&1 && diag PASS "apk" "менеджер пакунків знайдено" \
    || diag FAIL "apk" "не знайдено — це точно Alpine-термінал?"

MEM_KB=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || echo 0)
MEM_GB=$((MEM_KB / 1024 / 1024))
if [ "$MEM_GB" -ge 10 ]; then diag PASS "Оперативна пам'ять" "${MEM_GB}GB"
elif [ "$MEM_GB" -ge 6 ]; then diag WARN "Оперативна пам'ять" "${MEM_GB}GB — мінімум; великі книги можуть падати"
else diag FAIL "Оперативна пам'ять" "${MEM_GB}GB — потрібно щонайменше 6GB"; fi

FREE_GB=$(df -Pk "$HOME" 2>/dev/null | awk 'NR==2 {print int($4/1024/1024)}' || echo 0)
if [ "$FREE_GB" -ge 25 ]; then diag PASS "Вільне місце" "${FREE_GB}GB"
elif [ "$FREE_GB" -ge 15 ]; then diag WARN "Вільне місце" "${FREE_GB}GB — впритул (Ubuntu rootfs ~500MB + модель 4.4GB + контейнерні пакунки ~3-4GB)"
else diag FAIL "Вільне місце" "${FREE_GB}GB — потрібно щонайменше 15GB"; fi

if curl -s -m 8 -o /dev/null "https://github.com"; then diag PASS "Мережа" "github.com доступний"
else diag FAIL "Мережа" "github.com недоступний — перевірте інтернет"; fi
if curl -s -m 8 -o /dev/null "https://cdimage.ubuntu.com"; then diag PASS "Мережа" "cdimage.ubuntu.com доступний (звідти тягнеться Ubuntu rootfs)"
else diag WARN "Мережа" "cdimage.ubuntu.com недоступний — завантаження rootfs може не пройти"; fi

ADRENO_DETECTED=false
if [ -e /vendor/lib64/libOpenCL.so ]; then
    ADRENO_DETECTED=true
    diag PASS "GPU" "Adreno /vendor/lib64/libOpenCL.so видно навіть з-під Acode proot"
else
    diag WARN "GPU" "Adreno OpenCL не видно звідси (може бути прихований додатковим шаром proot Acode) — збірка буде CPU-only"
fi

warn "Acode може отримати обмеження батареї Android і вбити процес у фоні під час"
warn "довгого завантаження моделі (4.4GB) чи компіляції. Вимкніть оптимізацію"
warn "батареї для Acode (Налаштування → Застосунки → Acode → Батарея → Без обмежень)"
warn "і тримайте екран увімкненим на час встановлення."

if [ "$DIAG_FAILED" -ne 0 ]; then
    error "Діагностика виявила невиконані вимоги (FAIL вище). Виправте і запустіть знову."
fi
success "Діагностика пройдена."

# ---------------------------------------------------------------------------
# STEP 0b: Cheap nested-proot probe — the untested assumption this whole
# script depends on. Fail here (cheap) rather than after a 500MB download.
# ---------------------------------------------------------------------------
log "Перевірка: чи можна запустити другий proot всередині Acode's proot..."
if ! command -v proot >/dev/null 2>&1; then
    log "Встановлюю proot..."
    apk add --no-cache proot || error "apk add proot не вдався"
fi
PROOT_PROBE_DIR="$(mktemp -d)"
mkdir -p "$PROOT_PROBE_DIR/bin"
if proot -0 -r "$PROOT_PROBE_DIR" -b /proc -w / /bin/sh -c 'true' 2>/tmp/proot-probe.log; then
    success "Вкладений proot працює."
else
    echo "--- proot probe stderr ---"
    cat /tmp/proot-probe.log 2>/dev/null || true
    echo "---------------------------"
    error "Вкладений proot НЕ працює у цьому середовищі (ptrace conflict?). Далі йти немає сенсу — Ubuntu-контейнер для marker-pdf/calibre/torch не запуститься. Повідом це Q з виводом вище."
fi
rm -rf "$PROOT_PROBE_DIR"

# ---------------------------------------------------------------------------
# STEP 1: Alpine host packages.
# Ensure community repo is enabled (proot, opencl-headers, ocl-icd live
# there on most Alpine releases) — additive, idempotent.
# ---------------------------------------------------------------------------
log "Перевірка apk repositories (потрібен community repo)..."
ALPINE_VER=$(cut -d. -f1,2 /etc/alpine-release 2>/dev/null || echo "")
REPO_FILE="/etc/apk/repositories"
if [ -n "$ALPINE_VER" ] && [ -f "$REPO_FILE" ] && ! grep -q "/v${ALPINE_VER}/community" "$REPO_FILE" 2>/dev/null; then
    log "Додаю community repo (v${ALPINE_VER}) до $REPO_FILE..."
    echo "http://dl-cdn.alpinelinux.org/alpine/v${ALPINE_VER}/community" >> "$REPO_FILE"
fi

log "Встановлення пакунків хосту Alpine (apk)..."
apk update
# build-base = gcc/g++/make; opencl-headers+ocl-icd(-dev) for the native
# llama.cpp OpenCL build; ffmpeg/python3/py3-pip for the host Flask app.
# No libandroid-spawn equivalent needed: musl's libc ships spawn.h natively
# (this was a Termux/bionic-only gap).
apk add --no-cache \
    bash git curl wget tar xz ca-certificates rsync \
    build-base cmake ninja git \
    opencl-headers ocl-icd ocl-icd-dev clinfo \
    python3 py3-pip py3-pillow \
    ffmpeg \
    proot
success "Пакунки хосту Alpine встановлено."

PIP_EXTRA=""
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null && PIP_EXTRA="--break-system-packages" || true
pip3 install --upgrade pip $PIP_EXTRA || true
pip3 install Flask flask-httpauth requests tqdm marisa-trie blinker pypdf $PIP_EXTRA
success "Python-залежності хосту (Flask тощо) встановлено."

# ---------------------------------------------------------------------------
# STEP 2: llama.cpp — native build on Alpine host (fastest path to any
# Adreno GPU access; mirrors deploy.sh's Termux-side build).
# ---------------------------------------------------------------------------
if [ -x "$LLAMA_DIR/build/bin/llama-server" ]; then
    success "llama.cpp вже зібрано ($LLAMA_DIR/build/bin) — пропускаю."
else
    log "Збирання llama.cpp на хості Alpine (10-20 хв)..."
    CMAKE_GPU_FLAGS=""
    if [ "$ADRENO_DETECTED" = "true" ]; then
        CMAKE_GPU_FLAGS="-DGGML_OPENCL=ON -DGGML_OPENCL_USE_ADRENO_KERNELS=ON"
    fi
    if [ ! -d "$LLAMA_DIR/.git" ]; then
        git clone --depth 1 https://github.com/ggerganov/llama.cpp.git "$LLAMA_DIR"
    fi
    cd "$LLAMA_DIR"
    rm -rf build && mkdir -p build && cd build
    # GGML_NATIVE=OFF: avoids -mcpu=native ICEs seen on newest ARMv9 cores
    # with Termux clang; kept here defensively for Alpine's clang/gcc too.
    cmake .. $CMAKE_GPU_FLAGS -DGGML_NATIVE=OFF -DLLAMA_CURL=OFF \
        || error "llama.cpp cmake configure failed"
    make -j"$(nproc)" llama-server llama-cli \
        || error "llama.cpp build failed"
    cd "$HOME"
    [ -x "$LLAMA_DIR/build/bin/llama-server" ] || error "llama-server binary missing after build"
    success "llama.cpp зібрано ($CMAKE_GPU_FLAGS)."
fi

# ---------------------------------------------------------------------------
# STEP 3: Bootstrap Ubuntu 24.04 rootfs by hand (Alpine has no proot-distro
# package — this replicates what it does: download + extract a base
# tarball, no root required for extraction).
# ---------------------------------------------------------------------------
if [ -d "$ROOTFS_DIR/root" ]; then
    success "Ubuntu rootfs вже є ($ROOTFS_DIR) — пропускаю завантаження."
else
    log "Завантаження Ubuntu 24.04 base rootfs (arm64, ~35-70MB стиснено)..."
    TARBALL="$HOME/ubuntu-base-24.04-arm64.tar.gz"
    curl -L -C - --progress-bar -o "$TARBALL" "$UBUNTU_BASE_URL" \
        || error "Не вдалось завантажити Ubuntu base rootfs з $UBUNTU_BASE_URL"
    mkdir -p "$ROOTFS_DIR"
    log "Розпакування rootfs..."
    tar -xzf "$TARBALL" -C "$ROOTFS_DIR" \
        || error "Розпакування Ubuntu rootfs не вдалось"
    rm -f "$TARBALL"
    echo "nameserver 8.8.8.8" > "$ROOTFS_DIR/etc/resolv.conf"
    echo "nameserver 1.1.1.1" >> "$ROOTFS_DIR/etc/resolv.conf"
    success "Ubuntu rootfs готовий у $ROOTFS_DIR."
fi

# Launcher used both directly by the user and by the proot-distro shim.
LAUNCHER_PATH="$HOME/ubuntu-proot.sh"
log "Записую launcher контейнера в $LAUNCHER_PATH..."
{
    echo '#!/bin/bash'
    echo "ROOTFS=\"$ROOTFS_DIR\""
    echo 'GPU_BINDS=()'
    echo 'if [ -e /vendor/lib64/libOpenCL.so ]; then'
    echo '    GPU_BINDS=(-b /vendor:/vendor -b /system:/system -b /dev/kgsl:/dev/kgsl)'
    echo 'fi'
    cat << 'LAUNCHER_EOF'
exec proot --kill-on-exit -0 -r "$ROOTFS" \
    -b /dev -b /proc -b /sys -b /tmp \
    "${GPU_BINDS[@]+"${GPU_BINDS[@]}"}" \
    -w /root \
    /usr/bin/env -i HOME=/root PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    "$@"
LAUNCHER_EOF
} > "$LAUNCHER_PATH"
chmod +x "$LAUNCHER_PATH"
success "Launcher створено."

# ---------------------------------------------------------------------------
# STEP 3b: proot-distro shim — makes run_conversion_batches.py's hardcoded
# `proot-distro login ubuntu -- <cmd>` calls work unmodified.
# ---------------------------------------------------------------------------
log "Встановлюю proot-distro shim у $SHIM_DIR..."
mkdir -p "$SHIM_DIR"
cat > "$SHIM_DIR/proot-distro" << SHIM_EOF
#!/bin/bash
# proot-distro compatibility shim for Vydra on Alpine/Acode.
# Emulates ONLY the one invocation kindle-butch-gen's Python code uses:
#   proot-distro login ubuntu -- <command...>
# by delegating to the real launcher this installer wrote.
set -euo pipefail
if [ "\${1:-}" != "login" ] || [ "\${2:-}" != "ubuntu" ]; then
    echo "proot-distro-shim: only 'login ubuntu -- <cmd>' is emulated (got: \$*)" >&2
    exit 1
fi
shift 2
if [ "\${1:-}" = "--" ]; then shift; fi
exec "$LAUNCHER_PATH" "\$@"
SHIM_EOF
chmod +x "$SHIM_DIR/proot-distro"

case ":$PATH:" in
    *":$SHIM_DIR:"*) ;;
    *)
        warn "$SHIM_DIR не в PATH цієї сесії — додаю в ~/.profile для наступних сесій."
        echo "export PATH=\"$SHIM_DIR:\$PATH\"" >> "$HOME/.profile"
        export PATH="$SHIM_DIR:$PATH"
        ;;
esac
success "proot-distro shim встановлено."

# ---------------------------------------------------------------------------
# STEP 4: Clone kindle-butch-gen on the Alpine host (source of truth dir;
# stays outside the container, same as deploy.sh's Termux pattern).
# ---------------------------------------------------------------------------
log "Налаштування kindle-butch-gen..."
if [ -d "$PROJECT_DIR/.git" ]; then
    log "Вже клоновано в $PROJECT_DIR, оновлюю..."
    git -C "$PROJECT_DIR" pull --ff-only || warn "git pull не вдався (локальні зміни?) — продовжую з поточною версією."
else
    git clone "$REPO_URL" "$PROJECT_DIR"
fi
chmod +x "$PROJECT_DIR/kbg.sh" 2>/dev/null || true
success "kindle-butch-gen готовий у $PROJECT_DIR."

# ---------------------------------------------------------------------------
# STEP 5: Install the glibc-side ML stack inside the Ubuntu proot
# container (torch, marker-pdf, manga-ocr, mokuro, calibre, tesseract).
# ---------------------------------------------------------------------------
log "Встановлення ML-стеку всередині Ubuntu-контейнера (найдовший крок, 15-30 хв)..."
UBUNTU_SETUP_SCRIPT="$ROOTFS_DIR/root/ubuntu_setup.sh"
cat > "$UBUNTU_SETUP_SCRIPT" << 'SETUP_EOF'
#!/usr/bin/env bash
set -euo pipefail
echo "=== [Ubuntu Setup] ==="
export DEBIAN_FRONTEND=noninteractive
apt update
apt install -y --no-install-recommends \
    build-essential cmake git \
    python3-pip python3-venv libgomp1 \
    calibre ffmpeg tesseract-ocr tesseract-ocr-ukr \
    unrar-free p7zip-full wamerican \
    libfreetype6-dev libjpeg-dev zlib1g-dev libpng-dev python3-pil

echo "Installing Python ML dependencies (CPU torch — no CUDA on a phone)..."
pip install --upgrade pip --break-system-packages || true
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu --break-system-packages --ignore-installed
pip install marker-pdf pydantic transformers manga-ocr mokuro pytesseract stress-uk num2words --break-system-packages --ignore-installed
echo "=== [Ubuntu Setup Completed] ==="
SETUP_EOF
chmod +x "$UBUNTU_SETUP_SCRIPT"

set +e
"$LAUNCHER_PATH" -- bash -c "/root/ubuntu_setup.sh"
UBUNTU_SETUP_STATUS=$?
set -e
if [ "$UBUNTU_SETUP_STATUS" -ne 0 ]; then
    error "Налаштування Ubuntu-контейнера впало (exit $UBUNTU_SETUP_STATUS) — див. вивід вище."
fi
rm -f "$UBUNTU_SETUP_SCRIPT"
success "ML-стек у контейнері встановлено."

# ---------------------------------------------------------------------------
# STEP 6: Models (identical URLs/sizes to deploy.sh — resumable, verified).
# ---------------------------------------------------------------------------
check_and_download() {
    local label="$1" file_path="$2" url="$3" expected_size="$4"
    local dir_path; dir_path=$(dirname "$file_path")
    mkdir -p "$dir_path"
    if [ -f "$file_path" ]; then
        local actual_size; actual_size=$(stat -c%s "$file_path" 2>/dev/null || echo 0)
        if [ "$actual_size" -eq "$expected_size" ]; then
            success "$label вже є і перевірено ($actual_size байт)."
            return 0
        fi
        log "$label: розмір не збігається ($actual_size замість $expected_size). Перезавантажую."
    fi
    log "Завантаження $label..."
    while true; do
        if curl -L -C - --progress-bar -o "$file_path" "$url"; then
            local actual_size; actual_size=$(stat -c%s "$file_path" 2>/dev/null || echo 0)
            [ "$actual_size" -eq "$expected_size" ] && { success "$label завантажено ($actual_size байт)."; return 0; }
            echo -e "${RED}[ERROR]${NC} Завантаження $label неповне ($actual_size замість $expected_size)."
        else
            echo -e "${RED}[ERROR]${NC} curl впав під час завантаження $label."
        fi
        echo -n -e "${BLUE}[VYDRA]${NC} Повторити завантаження? (Y/n): "
        read -r retry || retry=""
        case "$retry" in [nN]*) log "Скасовано користувачем."; return 1 ;; *) ;; esac
    done
}

MODEL_DIR="$HOME/models/hy-mt2"
MODEL_PATH="$MODEL_DIR/Hy-MT2-7B-Q4_K_M.gguf"
HY_MT2_SIZE=4624650016
HY_MT2_URL="https://huggingface.co/mradermacher/Hy-MT2-7B-i1-GGUF/resolve/main/Hy-MT2-7B.i1-Q4_K_M.gguf"
check_and_download "Модель перекладу Hy-MT2-7B (4.4GB)" "$MODEL_PATH" "$HY_MT2_URL" "$HY_MT2_SIZE" || true

TTS_DIR="$PROJECT_DIR/models"
TTS_ARCHIVE="$TTS_DIR/sherpa-onnx-supertonic-3-tts-int8-2026-05-11.tar.bz2"
TTS_EXTRACTED="$TTS_DIR/sherpa-onnx-supertonic-3-tts-int8-2026-05-11"
TTS_SIZE=128774318
TTS_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/sherpa-onnx-supertonic-3-tts-int8-2026-05-11.tar.bz2"
if [ -d "$TTS_EXTRACTED" ] && [ -f "$TTS_EXTRACTED/vocoder.int8.onnx" ]; then
    success "Supertonic 3 TTS вже є."
else
    if check_and_download "Supertonic 3 TTS (129MB)" "$TTS_ARCHIVE" "$TTS_URL" "$TTS_SIZE"; then
        tar -xf "$TTS_ARCHIVE" -C "$TTS_DIR" && rm -f "$TTS_ARCHIVE"
        success "Supertonic 3 TTS розпаковано."
    fi
fi

# ---------------------------------------------------------------------------
# STEP 7: Web password (same scheme as deploy.sh).
# ---------------------------------------------------------------------------
PROFILE_FILE="$HOME/.profile"
if grep -q "^export KBG_WEB_PASSWORD=" "$PROFILE_FILE" 2>/dev/null; then
    WEB_PASSWORD=$(grep "^export KBG_WEB_PASSWORD=" "$PROFILE_FILE" | tail -1 | sed -E "s/^export KBG_WEB_PASSWORD=['\"]?//; s/['\"]?\$//")
else
    WEB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(12))")
    printf 'export KBG_WEB_PASSWORD='"'"'%s'"'"'\n' "$WEB_PASSWORD" >> "$PROFILE_FILE"
fi

echo -e "\n${GREEN}=====================================================================${NC}"
echo -e "${GREEN} Vydra (Alpine/Acode ARM64) встановлено!${NC}"
echo -e "${GREEN}=====================================================================${NC}"
echo -e " Веб-панель:  ${BLUE}http://localhost:5000${NC}  (логін admin / ${GREEN}${WEB_PASSWORD}${NC})"
echo -e " Запуск сервера перекладу (llama.cpp):"
if [ "$ADRENO_DETECTED" = "true" ]; then
    echo -e "   👉 $LLAMA_DIR/build/bin/llama-server -m $MODEL_PATH -c 4096 --port 8081 -ngl 99"
else
    echo -e "   👉 $LLAMA_DIR/build/bin/llama-server -m $MODEL_PATH -c 4096 --port 8081"
fi
echo -e " Запуск веб-панелі:"
echo -e "   👉 cd $PROJECT_DIR && python3 kbg_web/app.py --port 5000"
echo -e " Ручний вхід в Ubuntu-контейнер (для дебагу marker-pdf/calibre):"
echo -e "   👉 $LAUNCHER_PATH"
echo -e "${GREEN}=====================================================================${NC}\n"
