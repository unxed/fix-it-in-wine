/* lvpos: does LVM_GETITEMPOSITION return view or client coordinates after a
 * list-view scrolls, in icon and small-icon view?
 *
 * Microsoft documentation (LVM_GETITEMPOSITION): "In icon or small icon view,
 * the LVM_GETITEMPOSITION message returns the item's position in view
 * coordinates." So the position of an item must not change when the view
 * scrolls. WineHQ bug 59609: Wine returns client coordinates instead, so the
 * position moves by the scroll amount.
 *
 * Exit code: 0 - view coordinates in both views (as documented);
 *            1 - client coordinates in at least one view (bug 59609);
 *            2 - setup failed, the view did not scroll, or neither result.
 *
 * Build:     x86_64-w64-mingw32-gcc -O2 -Wall -o lvpos.exe lvpos.c -lcomctl32
 * With v6:   x86_64-w64-mingw32-windres lvpos6.rc -O coff -o lvpos6.res
 *            x86_64-w64-mingw32-gcc -O2 -Wall -o lvpos6.exe lvpos.c lvpos6.res -lcomctl32
 */
#include <windows.h>
#include <commctrl.h>
#include <shlwapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define ITEMS 200
#define PROBE 150
#define DX    300

static void print_comctl32(void)
{
    HMODULE h = GetModuleHandleA("comctl32.dll");
    char path[MAX_PATH] = "?";
    DLLVERSIONINFO vi;
    DLLGETVERSIONPROC get;

    if (!h) { puts("comctl32: not loaded"); return; }
    GetModuleFileNameA(h, path, sizeof(path));
    memset(&vi, 0, sizeof(vi));
    vi.cbSize = sizeof(vi);
    get = (DLLGETVERSIONPROC)(void *)GetProcAddress(h, "DllGetVersion");
    if (get && get(&vi) == S_OK)
        printf("comctl32 %lu.%lu.%lu: %s\n", vi.dwMajorVersion, vi.dwMinorVersion, vi.dwBuildNumber, path);
    else
        printf("comctl32 (no version): %s\n", path);
}

static int check(HWND parent, DWORD view, const char *name)
{
    HWND lv;
    LVITEMA it;
    POINT p0, p1, o0 = {0, 0}, o1 = {0, 0};
    int i, s0, s1, moved_x, moved_y, scrolled_x, scrolled_y, verdict;
    char text[16];

    lv = CreateWindowExA(0, WC_LISTVIEWA, "",
                         WS_CHILD | WS_VISIBLE | view | LVS_ALIGNLEFT | LVS_AUTOARRANGE,
                         0, 0, 400, 150, parent, NULL, GetModuleHandleA(NULL), NULL);
    if (!lv) { printf("%s: cannot create the list-view\n", name); return 2; }

    for (i = 0; i < ITEMS; i++)
    {
        memset(&it, 0, sizeof(it));
        it.mask = LVIF_TEXT;
        it.iItem = i;
        sprintf(text, "item %d", i);
        it.pszText = text;
        if (SendMessageA(lv, LVM_INSERTITEMA, 0, (LPARAM)&it) != i)
        {
            printf("%s: inserting item %d failed\n", name, i);
            DestroyWindow(lv);
            return 2;
        }
    }

    if (!SendMessageA(lv, LVM_GETITEMPOSITION, PROBE, (LPARAM)&p0))
    {
        printf("%s: LVM_GETITEMPOSITION failed\n", name);
        DestroyWindow(lv);
        return 2;
    }
    SendMessageA(lv, LVM_GETORIGIN, 0, (LPARAM)&o0);
    s0 = GetScrollPos(lv, SB_HORZ);

    SendMessageA(lv, LVM_SCROLL, DX, 0);

    SendMessageA(lv, LVM_GETITEMPOSITION, PROBE, (LPARAM)&p1);
    SendMessageA(lv, LVM_GETORIGIN, 0, (LPARAM)&o1);
    s1 = GetScrollPos(lv, SB_HORZ);

    moved_x = p0.x - p1.x;
    moved_y = p0.y - p1.y;
    scrolled_x = abs(o1.x - o0.x);
    scrolled_y = abs(o1.y - o0.y);

    printf("%s: origin (%ld,%ld) -> (%ld,%ld), scroll pos %d -> %d, item %d position (%ld,%ld) -> (%ld,%ld): ",
           name, o0.x, o0.y, o1.x, o1.y, s0, s1, PROBE, p0.x, p0.y, p1.x, p1.y);

    if (!scrolled_x && !scrolled_y && s0 == s1) { puts("did not scroll"); verdict = 2; }
    else if (!moved_x && !moved_y) { puts("view coordinates"); verdict = 0; }
    else if ((moved_x == scrolled_x && moved_y == scrolled_y) || (moved_x == s1 - s0 && !moved_y))
    { puts("client coordinates"); verdict = 1; }
    else { puts("neither"); verdict = 2; }

    DestroyWindow(lv);
    return verdict;
}

int main(void)
{
    INITCOMMONCONTROLSEX icc;
    HWND parent;
    int a, b;

    icc.dwSize = sizeof(icc);
    icc.dwICC = ICC_LISTVIEW_CLASSES;
    InitCommonControlsEx(&icc);
    print_comctl32();

    parent = CreateWindowExA(0, "STATIC", "lvpos", WS_OVERLAPPEDWINDOW, 0, 0, 420, 200,
                             NULL, NULL, GetModuleHandleA(NULL), NULL);
    if (!parent) { puts("cannot create the parent window"); return 2; }
    ShowWindow(parent, SW_SHOWNOACTIVATE);
    UpdateWindow(parent);

    a = check(parent, LVS_ICON, "icon");
    b = check(parent, LVS_SMALLICON, "smallicon");
    DestroyWindow(parent);

    if (a == 2 || b == 2) return 2;
    return (a || b) ? 1 : 0;
}
