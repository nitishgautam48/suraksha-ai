#!/bin/sh
# Pulls the local models into the Ollama service. Runs once in the `ollama-init` container.
# Safe to re-run: Ollama skips layers it already has.
set -e
: "${OLLAMA_HOST:=http://ollama:11434}"
export OLLAMA_HOST
for model in ${OLLAMA_MODELS:-nomic-embed-text llama3.1:8b gemma2:9b}; do
  echo ">>> pulling $model from the Ollama library"
  ollama pull "$model"
done
echo ">>> all models available:"
ollama list
