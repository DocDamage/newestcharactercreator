#!/usr/bin/env bash
# CI-only acquisition of the reviewed public tar/checksum pair. No extraction/run.
set -euo pipefail
if [[ "$#" != 1 || -z "${RUNNER_TEMP:-}" ]]; then
  echo "One runner-owned cache destination and RUNNER_TEMP are required" >&2
  exit 2
fi
directory="$1"
if [[ "$directory" != "$RUNNER_TEMP/ucc-blender-archive" || -L "$directory" ]]; then
  echo "Unexpected or redirected public archive cache destination" >&2
  exit 2
fi
mkdir -p "$directory"
entries="$(find "$directory" -mindepth 1 -maxdepth 1 -print -quit)"
if [[ -n "$entries" ]]; then
  echo "Refuse to replace a nonempty archive cache" >&2
  exit 2
fi
script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
staging="$(mktemp -d "$RUNNER_TEMP/ucc-blender-download.XXXXXXXX")"
archive='blender-5.3.0-linux-x64.tar.xz'
checksum='blender-5.3.0.sha256'
# Both origins are explicit. The fallback is delegated by mirror.blender.org and
# independently checked against the identical pinned 5.3.0 checksum bytes.
primary='https://download.blender.org/release/Blender5.3'
fallback='https://mirror.clarkson.edu/blender/release/Blender5.3'
request_id="${GITHUB_RUN_ID:?}-${GITHUB_RUN_ATTEMPT:?}-archive-cache"

classify_curl_failure() {
  local status="$1" classification
  classification="$(python3 "$script_directory/blender_archive_cache.py" classify-curl --exit-code "$status")" || return 20
  case "$classification" in
    10|20) echo "curl exit $status classified as $classification" >&2; return "$classification" ;;
    *) return 20 ;;
  esac
}

fetch_pair() {
  local origin="$1" suffix="$2" folder="$3" checksum_time="$4" archive_time="$5" status
  mkdir -p "$folder" || return 20
  # Do not follow redirects to another, unreviewed regional mirror. A redirect
  # fails as a transport/setup error; the explicit fallback below is the only one.
  if curl --fail --location --max-redirs 0 --proto '=https' --proto-redir '=https' \
      --retry 0 --connect-timeout 15 --max-time "$checksum_time" --max-filesize 65536 \
      --silent --show-error "$origin/$checksum$suffix" -o "$folder/$checksum"; then
    :
  else
    status="$?"
    classify_curl_failure "$status"
    return "$?"
  fi
  # A checksum/pin error is NOT a transport failure and never selects a fallback.
  if ! python3 "$script_directory/blender_archive_cache.py" checksum --input "$folder/$checksum"; then
    return 20
  fi
  if curl --fail --location --max-redirs 0 --proto '=https' --proto-redir '=https' \
      --retry 0 --connect-timeout 15 --max-time "$archive_time" --max-filesize 1073741824 \
      --silent --show-error "$origin/$archive$suffix" -o "$folder/$archive"; then
    :
  else
    status="$?"
    classify_curl_failure "$status"
    return "$?"
  fi
  if ! python3 "$script_directory/blender_archive_cache.py" verify --directory "$folder"; then
    return 20
  fi
}

if fetch_pair "$primary" "?ucc_ci=$request_id" "$staging/primary" 45 120; then
  selected="$staging/primary"
  echo "Public Blender archive source: $primary"
else
  failure="$?"
  if [[ "$failure" != 10 ]]; then
    exit "$failure"
  fi
  echo "Primary transport/setup failed; using the exact reviewed Clarkson fallback" >&2
  if fetch_pair "$fallback" '' "$staging/verified-clarkson" 60 240; then
    selected="$staging/verified-clarkson"
    echo "Public Blender archive source: $fallback"
  else
    exit "$?"
  fi
fi
cp -- "$selected/$archive" "$directory/$archive"
cp -- "$selected/$checksum" "$directory/$checksum"
python3 "$script_directory/blender_archive_cache.py" verify --directory "$directory"
# Staging remains runner-owned and is destroyed with the ephemeral job. No
# recursive deletion or copying of profiles, generated files or source assets.
