#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
pid_file="${repo_root}/.local-site.pid"
port="${PORT:-8000}"
conda_env="${CONDA_ENV:-structured_anarchy_py}"

if [[ ! "${port}" =~ ^[0-9]+$ ]] || ((port < 1 || port > 65535)); then
  echo "PORT must be an integer between 1 and 65535" >&2
  exit 1
fi

if [[ -f "${pid_file}" ]]; then
  server_pid="$(<"${pid_file}")"
  if [[ "${server_pid}" =~ ^[0-9]+$ ]] && kill -0 "${server_pid}" 2>/dev/null; then
    server_command="$(ps -p "${server_pid}" -o args= 2>/dev/null || true)"
    if [[ "${server_command}" == *"http.server"* && "${server_command}" == *"${repo_root}/dist"* ]]; then
      echo "Stopping local site (PID ${server_pid})..."
      kill "${server_pid}"
      wait "${server_pid}" 2>/dev/null || true
    else
      echo "Ignoring stale PID file; PID ${server_pid} is not this site's server." >&2
    fi
  fi
  rm -f -- "${pid_file}"
fi

if command -v lsof >/dev/null 2>&1; then
  while read -r listener_pid; do
    [[ "${listener_pid}" =~ ^[0-9]+$ ]] || continue
    listener_command="$(ps -p "${listener_pid}" -o args= 2>/dev/null || true)"
    if [[ "${listener_command}" == *"http.server"* ]]; then
      echo "Stopping existing HTTP server on port ${port} (PID ${listener_pid})..."
      kill "${listener_pid}"
    else
      echo "Port ${port} is already used by another service; refusing to stop it." >&2
      exit 1
    fi
  done < <(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)
fi

echo "Building site..."
conda run -n "${conda_env}" python "${repo_root}/scripts/build_site.py" \
  --root "${repo_root}" \
  --output "${repo_root}/dist"

python_bin="$(conda run -n "${conda_env}" python -c 'import sys; print(sys.executable)')"
if [[ ! -x "${python_bin}" ]]; then
  echo "Could not locate the ${conda_env} Python executable" >&2
  exit 1
fi

echo "Starting local site on http://localhost:${port}..."
"${python_bin}" -m http.server "${port}" -d "${repo_root}/dist" &
server_pid=$!
printf '%s\n' "${server_pid}" >"${pid_file}"

cleanup() {
  if kill -0 "${server_pid}" 2>/dev/null; then
    kill "${server_pid}" 2>/dev/null || true
  fi
  rm -f -- "${pid_file}"
}
trap cleanup EXIT INT TERM

echo "Local site is running (PID ${server_pid})."
wait "${server_pid}"
