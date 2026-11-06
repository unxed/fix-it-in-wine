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

FastStone is 32-bit. Build comctl32 for both architectures (`tools/build_one_dll.sh` does this)
and enable the `i386-windows` build for `FSViewer.exe` in your prefix:

```
git -C ~/.cache/fix-it-in-wine/src/wine-9.0 apply showcases/59609/fix.patch
tools/build_one_dll.sh wine-9.0 comctl32
tools/override.py apply --prefix ~/.wine --exe FSViewer.exe --dll ~/.cache/fix-it-in-wine/build/wine-9.0/dlls/comctl32/i386-windows/comctl32.dll
```

Use the tag of your Wine version (`wine --version`). If `tools/wineprobe.py run --dll comctl32`
shows that FastStone loads comctl32 from `winsxs` (version 6), use the side-by-side slot instead,
as in `run.sh`. Then open a folder with many images, press F, move the mouse to the top of the
screen and scroll the strip: the thumbnails must stay drawn.

## Results

See the latest run of the `showcase-59609` workflow and its summary.
