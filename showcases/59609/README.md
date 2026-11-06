# Showcase: WineHQ bug 59609 — FastStone thumbnail strip

[WineHQ bug 59609](https://bugs.winehq.org/show_bug.cgi?id=59609):
`LVM_GETITEMPOSITION` returns client coordinates instead of view coordinates in icon and
small-icon views. FastStone Image Viewer subtracts the scroll offset a second time, decides that
the thumbnails of its full-screen strip are off-screen, skips drawing them, and the strip shows
blank spaces. The fix is already in the ticket (comment 0, reporter T_Im). In the ticket, one
person could not reproduce the problem, and another asked for logs and evidence.

This showcase runs the fix-it-in-wine chain on that bug and records evidence that anyone can
rerun:

1. A minimal reproducer, `lvpos.c`: a list-view in icon and small-icon view scrolls by 300 pixels,
   and the program checks whether `LVM_GETITEMPOSITION` of one item changed. The Microsoft
   documentation says it must not change (view coordinates). Exit code 0 = view coordinates,
   1 = client coordinates (the bug), 2 = unclear. `lvpos6.exe` is the same program with a manifest
   for comctl32 version 6.
2. It runs on real Windows (GitHub Actions, `windows-latest`): the documented behaviour.
3. It runs on Wine from Ubuntu 24.04 (Wine 9.0) with the builtin comctl32: the bug.
4. comctl32 is built from the same Wine version with `fix.patch` (`tools/build_one_dll.sh`;
   only that DLL is built), enabled for the reproducer only (`tools/override.py`), and the
   reproducer runs again: expected fixed. Then the change is undone and the bug is back.

Everything above is in [`.github/workflows/showcase-59609.yml`](../../.github/workflows/showcase-59609.yml);
the Wine part is [`run.sh`](run.sh), which also runs on your own machine.

## Files

- `fix.patch` — the ticket's fix as a unified diff against wine-11.0; it also applies to wine-9.0.
- `lvpos.c`, `lvpos6.rc`, `lvpos6.manifest` — the reproducer.
- `run.sh` — the Wine part: before, build with the fix, enable, after, undo.

## Run it on your machine

```
x86_64-w64-mingw32-gcc -O2 -Wall -o lvpos.exe lvpos.c -lcomctl32
x86_64-w64-mingw32-windres lvpos6.rc -O coff -o lvpos6.res
x86_64-w64-mingw32-gcc -O2 -Wall -o lvpos6.exe lvpos.c lvpos6.res -lcomctl32
WINEPREFIX=/tmp/pfx59609 wineboot -i
WINEPREFIX=/tmp/pfx59609 bash run.sh .
```

Use a separate prefix: `run.sh` changes and then restores one comctl32 in it.

## For FastStone itself

The fix is now catalog entry
[`winehq-59609`](https://github.com/unxed/dllmgr/blob/main/catalog/fixes/winehq-59609.md) in
dllmgr. Its release and the one-step apply live there (decision D4: binaries are built by CI from
the catalog's source):

```
git clone https://github.com/unxed/dllmgr
dllmgr/scripts/apply-winehq-59609.sh
```

This showcase stays as the history of how the fix was found, built and checked.

## Results

Workflow run [42156695927](https://github.com/unxed/fix-it-in-wine/actions/runs/42156695927)
(2026-11-06), icon view, item 150, scroll by 300 pixels:

| Where | Builtin comctl32 | comctl32 built with `fix.patch` | After undo |
| --- | --- | --- | --- |
| Windows (`windows-latest`, comctl32 5.82 and 6.16) | `(2171,2) -> (2171,2)`: view coordinates | — | — |
| Wine 9.0 (Ubuntu) | `(2155,4) -> (1855,4)`: client coordinates, v5 and v6 | `(2155,4) -> (2155,4)`, v5 and v6 | bug back |
| Wine 11.0 (WineHQ stable) | same as 9.0 | same as 9.0 | bug back |
| Wine 11.21 (WineHQ devel) | same as 9.0 | same as 9.0 | bug back |

On Wine 11 the v6 case goes through the separate `comctl32_v6` module in the winsxs slot; it
works the same way.

Also seen, not part of 59609:
- in small-icon view Wine re-arranges the items when the view scrolls (`y` of the item changes),
  with and without the fix;
- `LVM_GETORIGIN` after scrolling right by 300 returns `(-300,0)` on Wine 9.0 and `(300,0)` on
  Windows and on Wine 11.

Draft comment for the WineHQ ticket: [report.md](report.md) (not posted).
