#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
  silma|audar) ;;
  edge|espeak) exit 0 ;;
  *) exit 2 ;;
esac

python -m pip install --index-url https://download.pytorch.org/whl/cpu \
  torch==2.8.0 torchaudio==2.8.0
case "$1" in
  silma)
    python -m pip install --index-url https://download.pytorch.org/whl/cpu torchvision==0.23.0
    python -m pip install "silma-tts==1.0.5" "transformers>=4.51,<5" "torchcodec==0.7.0"
    ;;
  audar)
    CMAKE_BUILD_PARALLEL_LEVEL=2 python -m pip install "llama-cpp-python==0.3.16" \
      "neucodec==0.0.6" "torchao==0.12.0" "transformers>=4.51,<5" "soundfile>=0.12,<1"
    ;;
esac
