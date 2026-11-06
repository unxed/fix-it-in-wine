# Showcases

| Showcase | Status |
| --- | --- |
| [WineHQ bug 59609](59609/README.md) — FastStone's thumbnail strip: the fix from the ticket, one DLL, one program, checked against Windows in CI | in progress |
| Far Manager 3 — stable work under Wine without modifying Far3 itself | planned |
| Adobe Photoshop trial — the final showcase | planned |

## Far Manager 3 (planned)

Goal: Far Manager 3 works stably under Wine with no change to Far3 itself. Every fix goes into
Wine DLLs (through the [dllmgr](https://github.com/unxed/dllmgr) catalog) or into patches over
DLLs that cannot be replaced.

Open: which problems Far3 hits under current Wine. The console side of Wine may involve DLLs that
cannot be replaced, in which case dllmgr patches (concept section 16) are needed.

## Photoshop trial (planned, the final one)

Goal: the Photoshop trial works under Wine. Several agents work in parallel during the trial
period, which limits the time: they test the program's areas and fix the bugs they find.

Prepare before the trial starts, so the trial time goes to testing and fixing: the list of areas
and scenarios, the split between agents, the reproducers.

Open: installation (the installer and Creative Cloud) under Wine.
