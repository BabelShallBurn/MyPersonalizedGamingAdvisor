#!/usr/bin/env bash
set -euo pipefail

python scripts/precompute_game_embeddings.py "$@"
