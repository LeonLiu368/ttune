#!/usr/bin/env bash
# Start the llama.cpp server on 127.0.0.1:8000, or restart it, and wait until it answers.
# Usage: llama-server.sh MODEL_FILE ALIAS N_CTX
#
# A restart is for a server that stops answering: when an agent times out, its last request is abandoned but
# the server keeps generating, and while it does, it answers nothing else.
set -u
if pgrep -f "llama_cpp.server" > /dev/null; then
  pkill -f "llama_cpp.server"
  for i in $(seq 1 10); do pgrep -f "llama_cpp.server" > /dev/null || break; sleep 1; done
  pkill -9 -f "llama_cpp.server" 2> /dev/null || true
fi
# logits_all False: the server otherwise keeps every token's logits (n_ctx x 152k floats, ~20 GB at 32k),
# which fills the runner's memory and slows each turn. Sampling only needs the last token's.
nohup python -m llama_cpp.server --model "$1" --model_alias "$2" \
  --n_ctx "$3" --n_threads "$(nproc)" --seed 0 --host 127.0.0.1 --port 8000 --verbose False --logits_all False \
  >> server.log 2>&1 &
for i in $(seq 1 120); do
  if curl -sf --max-time 5 http://127.0.0.1:8000/v1/models > /dev/null; then echo "server up after $((i * 5))s"; exit 0; fi
  sleep 5
done
echo "server didn't start:"; tail -50 server.log; exit 1
