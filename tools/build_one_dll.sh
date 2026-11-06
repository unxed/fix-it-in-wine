#!/usr/bin/env bash
# Build selected Wine DLLs from one source ref (tag, branch or commit).
# Usage: build_one_dll.sh <ref> <dll> [<dll>...]
#
# $src is the work tree: apply patches there (git apply) and rerun; only
# changed files rebuild.
#
# Checked on Ubuntu 24.04 with wine-11.0: configure 19 s, tools 9 s,
# comctl32 + comctl32_v6 39 s, rebuild after one file 4 s.
# No tests (CI runs bash -n).
set -euo pipefail

if [ $# -lt 2 ]; then
    echo "usage: $0 <ref> <dll> [<dll>...]" >&2
    exit 1
fi
ref=$1
shift

# Check required tools
missing=()
for t in git gcc make flex bison i686-w64-mingw32-gcc x86_64-w64-mingw32-gcc; do
    command -v "$t" >/dev/null 2>&1 || missing+=("$t")
done
if [ ${#missing[@]} -gt 0 ]; then
    echo "missing tools: ${missing[*]}" >&2
    echo "Debian/Ubuntu/Mint: sudo apt install git gcc make flex bison gcc-mingw-w64-i686 gcc-mingw-w64-x86-64" >&2
    exit 2
fi

W=${FIW_WORK:-$HOME/.cache/fix-it-in-wine}
src=$W/src/$ref
bld=$W/build/$ref
GIT=${FIW_WINE_GIT:-https://gitlab.winehq.org/wine/wine.git}
J=${JOBS:-$(nproc)}

# Fetch source: clone the ref, or fetch it by commit id
if [ ! -d "$src/.git" ]; then
    mkdir -p "$(dirname "$src")"
    if ! git clone -q --depth 1 --branch "$ref" "$GIT" "$src"; then
        rm -rf "$src"
        git init -q "$src"
        git -C "$src" fetch -q --depth 1 "$GIT" "$ref"
        git -C "$src" checkout -q FETCH_HEAD
    fi
fi

# Configure once per ref
if [ ! -f "$bld/Makefile" ]; then
    mkdir -p "$bld"
    if ! (cd "$bld" && "$src/configure" --enable-archs=i386,x86_64 --without-x --without-freetype > configure.log 2>&1); then
        tail -n 20 "$bld/configure.log" >&2
        exit 3
    fi
fi

# Build the tools and the requested DLLs
targets=(__tooldeps__)
for d in "$@"; do
    targets+=("dlls/$d/all")
done
if ! make -C "$bld" -j"$J" "${targets[@]}" > "$bld/make.log" 2>&1; then
    grep -i error "$bld/make.log" | head -n 20 >&2 || true
    exit 4
fi

# List the built DLLs
for d in "$@"; do
    for f in "$bld/dlls/$d"/{i386,x86_64}-windows/*.dll; do
        if [ -e "$f" ]; then
            echo "$f"
        fi
    done
done
