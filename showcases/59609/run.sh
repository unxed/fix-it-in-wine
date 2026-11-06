#!/usr/bin/env bash
# Showcase for WineHQ bug 59609, end to end with the fix-it-in-wine tools:
# run the reproducer on the system Wine, build comctl32 from the same Wine version with
# fix.patch, enable it for the reproducer only, run again, undo, run again.
#
# Usage: run.sh BIN_DIR
#   BIN_DIR holds lvpos.exe and lvpos6.exe (64-bit, built from lvpos.c, see README.md).
#   WINEPREFIX must point to an initialised 64-bit prefix. Needs the build packages
#   listed by tools/build_one_dll.sh. FIW_WORK and FIW_WINE_GIT work as in that script.
# Exit 0 when the fix works as described: lvpos.exe gives 1 (bug) before, 0 after, 1 after undo.
set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd)
tools=$here/../../tools
bin=$(cd "${1:?usage: run.sh BIN_DIR}" && pwd)
: "${WINEPREFIX:?set WINEPREFIX}"
tag=$(wine --version | cut -d' ' -f1)
src=${FIW_WORK:-$HOME/.cache/fix-it-in-wine}/src/$tag
sxs_slot='sxs:amd64_microsoft.windows.common-controls_6595b64144ccf1df_6.*'

step() { echo; echo "== $*"; }
lv() { local rc; wine "$bin/$1.exe" 2>/dev/null; rc=$?; echo "$1.exe: exit $rc"; return $rc; }

step "$(wine --version), builtin comctl32"
lv lvpos; before=$?
lv lvpos6; before6=$?
python3 "$tools/wineprobe.py" run --prefix "$WINEPREFIX" --dll comctl32 --timeout 60 -- "$bin/lvpos.exe"

step "build comctl32 from $tag with fix.patch"
if [ ! -d "$src/.git" ]; then
    git clone -q --depth 1 --branch "$tag" "${FIW_WINE_GIT:-https://gitlab.winehq.org/wine/wine.git}" "$src" || exit 2
fi
if git -C "$src" apply --check "$here/fix.patch" 2>/dev/null; then
    git -C "$src" apply "$here/fix.patch" || exit 2
elif ! git -C "$src" apply --reverse --check "$here/fix.patch" 2>/dev/null; then
    echo "fix.patch does not apply to $tag"; exit 2
fi
built=$(bash "$tools/build_one_dll.sh" "$tag" comctl32) || exit 2
echo "$built"
dll=$(echo "$built" | grep x86_64-windows)

step "enable it for lvpos.exe (system slot) and lvpos6.exe (side-by-side slot) only"
python3 "$tools/override.py" apply --prefix "$WINEPREFIX" --exe lvpos.exe --dll "$dll" || exit 2
python3 "$tools/override.py" apply --prefix "$WINEPREFIX" --exe lvpos6.exe --dll "$dll" \
    --name comctl32.dll --slot "$sxs_slot"; sxs=$?

step "after"
lv lvpos; after=$?
lv lvpos6; after6=$?
python3 "$tools/wineprobe.py" run --prefix "$WINEPREFIX" --dll comctl32 --timeout 60 -- "$bin/lvpos.exe"

step "undo"
python3 "$tools/override.py" undo --prefix "$WINEPREFIX" --exe lvpos.exe --name comctl32
[ "$sxs" = 0 ] && python3 "$tools/override.py" undo --prefix "$WINEPREFIX" --exe lvpos6.exe --name comctl32
lv lvpos; undone=$?

step "summary (0 = view coordinates, as documented; 1 = client coordinates, bug 59609; 2 = unclear)"
echo "$(wine --version)"
echo "v5 (lvpos.exe):  before $before, after $after, after undo $undone"
echo "v6 (lvpos6.exe): before $before6, after $after6, side-by-side slot $([ "$sxs" = 0 ] && echo applied || echo failed)"
[ "$before" = 1 ] && [ "$after" = 0 ] && [ "$undone" = 1 ]
