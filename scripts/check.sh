#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python3 scripts/validate_plugin.py .
python3 scripts/generate_cli_docs.py --check
python3 -m unittest discover -s tests -v
