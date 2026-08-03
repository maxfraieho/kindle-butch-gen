#!/data/data/com.termux/files/usr/bin/bash
# Script to start llama-server for Hy-MT2-7B translation model on port 8081
# Model: Hy-MT2-7B-Q4_K_M (4.4GB) — translation-specific EN/RU → UK
#
# Stopping any previous instance is the caller's responsibility
# (kbg_web/app.py's /api/models/start stops the old process via the PID
# file before invoking this script) — this script only launches and
# records its own PID. It does not pkill anything itself (see TASK-18:
# a duplicate pkill here used to race against the API-layer pkill and
# could leave two llama-server processes running).

termux-wake-lock

export LD_LIBRARY_PATH="$HOME:/system/lib64:/vendor/lib64:$PREFIX/opt/vendor/lib:$HOME/llama.cpp/build/bin"

# Hardcoded, not derived from $BASH_SOURCE: the deployed copy of this
# script (~/start-translation-server.sh) lives directly in $HOME, not in
# kindle-butch-gen/bin/ -- "dirname($BASH_SOURCE)/.." silently resolved
# to $HOME/.. there (global_settings.json never found, MODEL always
# fell through to the hardcoded Hy-MT2 default). Hardcoding here too so
# this git-tracked copy behaves identically regardless of where it's
# deployed, instead of only working by the coincidence of currently
# sitting at repo_root/bin/.
REPO_DIR="$HOME/kindle-butch-gen"
# TASK-90 Stage 9 fix: _swap_llama_server() (kbg_web/app.py) writes
# "active_model" for editor-model swaps, NEVER "translation_model" (Q-15 --
# that key is the user's configured translation preference and must not be
# clobbered by a swap). This script previously only ever read
# "translation_model", so a swap to the editor model silently loaded Hy-MT2
# instead -- no error anywhere, the model-swap mechanism just didn't work.
# active_model takes priority now; translation_model is the fallback for
# the normal (non-swap) translation path, unchanged.
MODEL=$(python3 -c "import json, os; s_path=os.path.join('${REPO_DIR}', 'global_settings.json'); home=os.path.expanduser('~'); default_m=os.path.join(home, 'models/hy-mt2/Hy-MT2-7B-Q4_K_M.gguf'); data=json.load(open(s_path)) if os.path.exists(s_path) else {}; print(os.path.expanduser(data.get('active_model') or data.get('translation_model') or default_m))")
PORT=8081
PID_FILE="${1:-$HOME/llama-server-8081.pid}"

# Symmetric q8_0 KV cache is bake-off-VERIFIED only for the editor
# model (Qwen2.5-3B, agents/book_editor/agent.json) -- applying it
# unconditionally to Hy-MT2 (the translation model) would be an
# untested change to the core, heavily-used translation path (Opus-
# audit caught this: it was silently unconditional). Detect editor-
# model launches by path (case-insensitive "qwen") and only enable
# the flags there; Hy-MT2 keeps its previously-verified default (no
# explicit -ctk/-ctv -> llama-server's own default, f16/f16).
KV_CACHE_ARGS=()
if echo "$MODEL" | command grep -qi "qwen"; then
    KV_CACHE_ARGS=(-ctk q8_0 -ctv q8_0)
fi

echo "$(date): Запуск моделі на порту $PORT ($MODEL)..."

cd ~/llama.cpp/build/bin
nohup ./llama-server \
  -m "$MODEL" \
  -c 4096 \
  -ngl 99 \
  --parallel 1 \
  -t 4 \
  --no-mmap \
  "${KV_CACHE_ARGS[@]}" \
  --host 0.0.0.0 \
  --port "$PORT" \
  > ~/llama-translation-server.log 2>&1 & disown
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"
echo "$(date): llama-server started (PID: $SERVER_PID) on port $PORT for Hy-MT2-7B" >> ~/llama-boot.log
echo "PID: $SERVER_PID — waiting for server to be ready..."

# Wait for server to be ready
for i in $(seq 1 60); do
  sleep 2
  if LD_LIBRARY_PATH="" curl -s http://127.0.0.1:$PORT/health | grep -q "ok\|healthy"; then
    echo "Server ready after ${i}*2 seconds!"
    break
  fi
  echo -n "."
done
echo ""
echo "Server status: $(curl -s http://localhost:$PORT/health 2>/dev/null || echo 'not ready yet')"
