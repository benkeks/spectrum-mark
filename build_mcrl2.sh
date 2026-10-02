#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
build_dir="$repo_dir/build/mcrl2"
jobs=${JOBS:-2}

if [[ ! "$jobs" =~ ^[1-9][0-9]*$ ]]; then
    printf 'JOBS must be a positive integer.\n' >&2
    exit 1
fi

git -C "$repo_dir" submodule update --init --depth 1 mcrl2
cmake -S "$repo_dir/mcrl2" -B "$build_dir" \
    -DCMAKE_BUILD_TYPE=Release \
    -DMCRL2_ENABLE_GUI_TOOLS=OFF \
    -DMCRL2_ENABLE_DOCUMENTATION=OFF \
    -DMCRL2_ENABLE_DOC_MANUAL=OFF \
    -DMCRL2_ENABLE_TESTS=OFF \
    -DMCRL2_ENABLE_TOOL_TESTS=OFF \
    -DMCRL2_ENABLE_SYLVAN=OFF
cmake --build "$build_dir" --config Release --target ltscompare --parallel "$jobs"

printf '\nltscompare built under %s/stage/bin\n' "$build_dir"