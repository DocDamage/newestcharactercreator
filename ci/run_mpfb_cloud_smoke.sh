#!/usr/bin/env bash
# One-time, isolated integration test: official Blender + MPFB, real mesh/rig only.
# No user files, models, purchased art, checkpoints or .blend outputs leave the runner.
set -euo pipefail
: "$RUNNER_TEMP"
workdir="$RUNNER_TEMP/ucc-blender"
export BLENDER_USER_CONFIG="$RUNNER_TEMP/ucc-blender-config"
export BLENDER_USER_SCRIPTS="$RUNNER_TEMP/ucc-blender-scripts"
mkdir -p "$workdir" "$BLENDER_USER_CONFIG" "$BLENDER_USER_SCRIPTS"
cd "$workdir"
origin='https://download.blender.org/release/Blender5.3'
echo 'Downloading official Blender 5.3.0 and detached checksum listing'
curl --fail --location --retry 3 --silent --show-error --max-time 900 \
  "$origin/blender-5.3.0-linux-x64.tar.xz" -o blender-5.3.0-linux-x64.tar.xz
curl --fail --location --retry 3 --silent --show-error --max-time 90 \
  "$origin/blender-5.3.0.sha256" -o blender-5.3.0.sha256
grep -E '^[a-fA-F0-9]{64} [ *]blender-5\.3\.0-linux-x64\.tar\.xz$' blender-5.3.0.sha256 | sha256sum --check --strict
tar -xf blender-5.3.0-linux-x64.tar.xz
blender="$(find "$workdir" -maxdepth 3 -type f -name blender | head -n 1)"
test -n "$blender" && test -x "$blender"
"$blender" --background --version | head -n 5
cd "$GITHUB_WORKSPACE"
echo 'Installing MPFB via official Blender Extensions repository, isolated from any user machine'\necho 'Temporary online mode is used only for extension installation; generation stays offline.'
"$blender" --command extension repo-add ucc_blender_org \
  --name 'Blender Extensions' --url 'https://extensions.blender.org/api/v1/extensions/'
"$blender" --online-mode --command extension sync
"$blender" --command extension repo-info ucc_blender_org
"$blender" --online-mode --command extension install -s -e mpfb
"$blender" --command extension list | grep -i mpfb
echo 'Generating ACTUAL humanoid mesh and rig; saving and reopening in a separate Blender process'
result="$RUNNER_TEMP/ucc-mpfb-smoke"
if ! python3 Stage0_Starter/tools/run_mpfb_smoke.py \
  --blender "$blender" --outdir "$result" --timeout 300; then
  echo 'Real MPFB smoke FAILED. Available JSON diagnostics:'
  for item in "$result"/summary.json "$result"/mpfb_create_result.json "$result"/reopen_result.json; do
    if test -f "$item"; then echo "--- $(basename "$item") ---"; head -c 15000 "$item"; echo; fi
  done
  exit 1
fi
python3 - "$result" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
created = json.loads((root/'mpfb_create_result.json').read_text(encoding='utf8'))
reopened = json.loads((root/'reopen_result.json').read_text(encoding='utf8'))
conditions = [
    created.get('status') == 'ok',
    created.get('method') == 'HumanService',
    created.get('rig_choice') == 'default',
    any(r.get('bone_count', 0) >= 5 for r in created.get('rigs', [])),
    reopened.get('status') == 'ok',
    reopened.get('armature_count', 0) >= 1,
    reopened.get('vertex_count', 0) > 100,
    reopened.get('bone_count', 0) >= 5,
]
if not all(conditions):
    raise SystemExit('REAL_MPFb_VALIDATION_INCOMPLETE: one or more mesh/rig/reopen conditions failed')
print('REAL_LINUX_BLENDER_MPFb_MESH_RIG_REOPEN_PASSED')
print('Windows compatibility, deformation and engine import remain untested')
PY
