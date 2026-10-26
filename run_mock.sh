#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js is required for the dev frontend." >&2
  exit 1
fi

if [[ -n "${ALFA_MOCK_PYTHON:-}" ]]; then
  PYTHON="$(command -v -- "$ALFA_MOCK_PYTHON" || true)"
  if [[ -z "$PYTHON" || ! -x "$PYTHON" ]]; then
    echo "ALFA_MOCK_PYTHON is not executable: $PYTHON" >&2
    exit 1
  fi
  if ! "$PYTHON" -c 'import jsonschema, numpy' >/dev/null 2>&1; then
    echo "Install service/requirements.lock into ALFA_MOCK_PYTHON first." >&2
    exit 1
  fi
else
  PYTHON="$ROOT/.venv-mock/bin/python"
  if [[ ! -x "$PYTHON" ]]; then
    if ! command -v python3.12 >/dev/null 2>&1; then
      echo "Python 3.12 is required for the mock API." >&2
      exit 1
    fi
    python3.12 -m venv "$ROOT/.venv-mock"
  fi
  if ! "$PYTHON" -c 'import jsonschema, numpy' >/dev/null 2>&1; then
    "$PYTHON" -m pip install -r service/requirements.lock
  fi
fi

if [[ ! -f frontend/node_modules/next/package.json ]]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "Node.js and npm are required for the dev frontend." >&2
    exit 1
  fi
  npm --prefix frontend ci
fi

exec "$PYTHON" -m tools.mock_dev "$@"
