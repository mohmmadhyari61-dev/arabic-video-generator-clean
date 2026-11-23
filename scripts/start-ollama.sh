#!/usr/bin/env bash
set -euo pipefail

install_dir="${RUNNER_TEMP:-/tmp}/lecture-ollama"
mkdir -p "$install_dir"
archive="$install_dir/ollama.tar.zst"
curl -fLsS --retry 3 --max-time 240 \
  https://github.com/ollama/ollama/releases/download/v0.32.13/ollama-linux-amd64.tar.zst \
  -o "$archive"
printf '%s  %s\n' 0fd1dece38a1c6242e8013ce20b597345c5de072ae6b320160edb0e729ef1de1 "$archive" | sha256sum --check -
tar --zstd -xf "$archive" -C "$install_dir"
rm "$archive"

export OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_MODELS="$install_dir/models" OLLAMA_CONTEXT_LENGTH=8192
"$install_dir/bin/ollama" serve > "$install_dir/server.log" 2>&1 &
for attempt in {1..60}; do
  if curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
    "$install_dir/bin/ollama" pull qwen3:4b
    exit 0
  fi
  sleep 1
done
cat "$install_dir/server.log" >&2
exit 1
