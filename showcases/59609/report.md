# Draft comment for WineHQ bug 59609 (not posted)

Posted only after the owner's approval, under the owner's account.

---

Confirmed with a minimal test program on Windows and on Wine 9.0, 11.0 and 11.21.

Test: a list-view with 200 items (`LVS_ALIGNLEFT | LVS_AUTOARRANGE`, 400x150) in `LVS_ICON` and
in `LVS_SMALLICON` view, once without and once with a common controls 6 manifest. The program
reads `LVM_GETITEMPOSITION` of item 150, sends `LVM_SCROLL` with dx = 300, and reads it again.

- Windows (GitHub Actions `windows-latest`, comctl32 5.82.10586 and 6.16.10586): the position
  does not change, for example icon view (2171,2) -> (2171,2). This matches the documentation:
  view coordinates in icon and small icon view.
- Wine 9.0 (Ubuntu package), 11.0 and 11.21 (WineHQ packages), builtin comctl32: icon view
  (2155,4) -> (1855,4), the position moves by the scroll amount (client coordinates); the same
  with comctl32 v6.
- With the change from the description applied to `dlls/comctl32/listview.c` and comctl32
  (and comctl32_v6 on 11.x) built from the wine-9.0, wine-11.0 and wine-11.21 tags: icon view
  (2155,4) -> (2155,4), with and without the v6 manifest.

Test program source: https://github.com/unxed/fix-it-in-wine/blob/main/showcases/59609/lvpos.c
CI logs (all three Wine versions and Windows): https://github.com/unxed/fix-it-in-wine/actions/runs/42156695927
The change as a patch against wine-11.0 (applies to wine-9.0 too): https://github.com/unxed/fix-it-in-wine/blob/main/showcases/59609/fix.patch
FastStone download: see the URL field of this bug; the steps are in comment 5.

Seen with the same program, not part of this bug:
- in small icon view Wine re-arranges the items when the view scrolls (the item's y changes),
  with and without the change;
- `LVM_GETORIGIN` after scrolling right by 300 returns (-300,0) on Wine 9.0, and (300,0) on
  Windows and on Wine 11.0 and 11.21.
