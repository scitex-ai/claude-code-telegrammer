#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work_dir="$(mktemp -d "${TMPDIR:-/tmp}/cct-wheel-test.XXXXXX")"
trap 'rm -rf "$work_dir"' EXIT
python_bin="${CCT_TEST_PYTHON:-python3}"

"$python_bin" -m build --outdir "$work_dir/dist" "$repo_root"
wheel="$(find "$work_dir/dist" -maxdepth 1 -name '*.whl' -print -quit)"
test -n "$wheel"

"$python_bin" -m venv "$work_dir/venv"
"$work_dir/venv/bin/python" -m pip install --no-deps "$wheel"

package_dir="$work_dir/venv/lib"
server="$(find "$package_dir" -path '*/site-packages/claude_code_telegrammer/ts/telegram-server.ts' -print -quit)"
test -f "$server"
test -f "$(dirname "$server")/telegram-poller.ts"
test -f "$(dirname "$server")/package.json"
test -f "$(dirname "$server")/bun.lock"
test -f "$(dirname "$server")/lib/config.ts"
test ! -e "$(dirname "$server")/test"

fake_bun="$work_dir/fake-bun"
args_file="$work_dir/bun-args"
cat >"$fake_bun" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" >"$CCT_TEST_ARGS_FILE"
EOF
chmod +x "$fake_bun"

env BUN_BIN="$fake_bun" CCT_TEST_ARGS_FILE="$args_file" \
    "$work_dir/venv/bin/claude-code-telegrammer" config --check

expected="$(printf 'run\n%s\nconfig\n--check\n' "$server")"
actual="$(cat "$args_file")"
test "$actual" = "$expected"
