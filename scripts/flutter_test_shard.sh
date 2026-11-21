#!/bin/bash
# ============================================================================
# flutter_test_shard.sh I/N — run shard I of N of app/test under the build cap.
#
# Each shard is one manual-stage hook (ci-mirror-flutter-test-1..N) so no call
# nears the 60 s action cap. A bare `flutter test` on the shared /tmp held a
# build slot 63-67 s under the build queue (perf.heavybuild, 2026-11-21) while
# the whole suite takes ~8 s alone: a sibling run deleted the shared
# /tmp/flutter_tools.* dir and this one stalled. So each shard gets its own
# TMPDIR and two isolates (the default, one per core, overruns capped.sh).
#
# A shard that went green on the exact same app/ tree is not run again: the
# stamp is keyed on every file under app/lib, app/test and the pubspecs, plus
# this script and the shard's file list. Only a green run writes a stamp.
# ============================================================================

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
readonly ROOT
readonly APP_DIR="$ROOT/app"
readonly STAMP_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/leetcode-guard-flutter-test"

log() { printf 'flutter-test: %s\n' "$1" >&2; }
fail() {
    log "FAILED — $1"
    exit 1
}

# Every input the shard's result depends on, hashed into one key: every
# non-ignored file under app/ (assets, web/, tool/ and fixtures count, not just
# lib/ and test/), this script, the shard's file list and the Flutter SDK.
# A key that misses an input would replay a green over a red tree.
tree_key() {
    local file
    {
        printf '%s\n' "$@"
        sha256sum <"${BASH_SOURCE[0]}"
        sdk_identity
        git -C "$ROOT" ls-files -co --exclude-standard -z -- app | LC_ALL=C sort -z \
            | while IFS= read -r -d '' file; do
                [[ -f "$ROOT/$file" ]] && sha256sum -- "$ROOT/$file"
            done
    } | sha256sum | cut -d' ' -f1
}

# The SDK's version file, read directly: `flutter --version` would queue on
# the machine-wide build lock just to say the cache is still good.
sdk_identity() {
    local bin dir
    while IFS= read -r bin; do
        dir="$(dirname "$(readlink -f "$bin")")"
        if [[ -f "$dir/cache/flutter.version.json" ]]; then
            cat "$dir/cache/flutter.version.json"
            return 0
        fi
    done < <(type -ap flutter)
    echo "sdk-unknown"
}

# `flutter test` re-resolves packages online on every call (~6 s of an 8 s
# one-file run, 2026-11-21), so resolve once, offline first, only when the
# pubspecs are newer than the package config, and run the tests with --no-pub.
ensure_packages() {
    local config="$APP_DIR/.dart_tool/package_config.json"
    if [[ -f "$config" && ! "$APP_DIR/pubspec.yaml" -nt "$config" \
        && ! "$APP_DIR/pubspec.lock" -nt "$config" ]]; then
        return 0
    fi
    log "resolving packages (pubspec changed)"
    flutter_app pub get --offline || flutter_app pub get || fail "flutter pub get"
}

flutter_app() {
    (cd "$APP_DIR" && env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE flutter "$@")
}

main() {
    [[ ${1:-} =~ ^([0-9]+)/([1-9][0-9]*)$ ]] || fail "usage: flutter_test_shard.sh I/N, got '${1:-}'"
    local index=${BASH_REMATCH[1]} total=${BASH_REMATCH[2]} hooks i=0 file key
    hooks="$(grep -c '^ *- id: ci-mirror-flutter-test-[0-9]' "$ROOT/.pre-commit-config.yaml" || true)"
    ((total == hooks && index < total)) \
        || fail "shard $index/$total does not match the $hooks ci-mirror-flutter-test-N hooks"

    local -a files=()
    while IFS= read -r file; do
        ((i % total == index)) && files+=("${file#"$APP_DIR"/}")
        i=$((i + 1))
    done < <(find "$APP_DIR/test" -name '*_test.dart' | LC_ALL=C sort)
    ((${#files[@]} > 0)) || fail "shard $index/$total has no test files"

    key="$(tree_key "$index/$total" "${files[@]}")"
    if [[ -f "$STAMP_DIR/$key" ]]; then
        log "shard $index/$total cached green (app/ unchanged)"
        return 0
    fi

    log "shard $index/$total (${#files[@]} files)"
    local tmp status=0
    mkdir -p "$STAMP_DIR"
    tmp="$(mktemp -d "$STAMP_DIR/tmp.XXXXXX")"
    ensure_packages
    TMPDIR="$tmp" flutter_app test --no-pub \
        --concurrency="${FLUTTER_TEST_CONCURRENCY:-2}" "${files[@]}" || status=$?
    rm -rf -- "$tmp"
    ((status == 0)) || fail "flutter test shard $index/$total"
    : >"$STAMP_DIR/$key"
}

main "$@"
