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

One command, for FastStone only (32-bit or 64-bit, Wine 9 or 11):

```
git clone https://github.com/unxed/fix-it-in-wine
fix-it-in-wine/showcases/59609/apply.sh
```

It finds `FSViewer.exe` in `WINEPREFIX` (default `~/.wine`; pass `--exe PATH` for a portable
copy), checks its manifest to choose comctl32 v5 (system directory) or v6 (winsxs), downloads
the fixed DLL for your exact `wine --version` from the
[fix-59609 release](https://github.com/unxed/fix-it-in-wine/releases/tag/fix-59609) (checked
against SHA256SUMS), and enables it for `FSViewer.exe` only. If the release has no file for your
Wine version, it builds one here (`--build` forces that). Undo: `apply.sh --undo`.

Then open a folder with many images, press F, move the mouse to the top of the screen and scroll
the strip: the thumbnails must stay drawn.

The release is built by [`release-59609.yml`](../../.github/workflows/release-59609.yml) from the
Wine tags listed in its `SOURCE.txt` plus `fix.patch`.

## Results

First run (workflow run 42155031164, 2026-11-06):

- **Windows** (`windows-latest`, comctl32 5.82 and 6.16): in icon and small-icon view the item
  position does not change after a 300-pixel scroll — view coordinates, as documented.
- **Wine 9.0 (Ubuntu), builtin comctl32:** icon view `(2155,4) -> (1855,4)` — client
  coordinates: bug 59609.
- **The same Wine with comctl32 built from wine-9.0 with `fix.patch`**, enabled for the
  reproducer only: icon view `(2155,4) -> (2155,4)` — view coordinates, both through the system
  directory (v5) and through the winsxs copy (v6). Undo brings the bug back.
- **Also seen, not part of 59609:** in small-icon view Wine re-arranges the items when the view
  scrolls (`y` 42 -> 84, with and without the fix); `LVM_GETORIGIN` after scrolling right by 300
  returns `(300,0)` on Windows and `(-300,0)` on Wine.

That run reported exit code 2 on Wine, because the reproducer then compared both axes; it now
judges the scroll axis and prints a change of `y` as a note. WineHQ stable and devel: pending.
