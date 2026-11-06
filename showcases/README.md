# Showcases

| Showcase | Status |
| --- | --- |
| [WineHQ bug 59609](59609/README.md) — FastStone's thumbnail strip: the fix from the ticket, one DLL, one program, checked against Windows in CI | in progress |
| Far Manager 3 — stable work under Wine without modifying Far3 itself | planned |
| Adobe Photoshop trial | possible, not planned |
| The final showcase: a program with no alternative on Linux, now or expected | to be chosen |

## Far Manager 3 (planned)

Goal: Far Manager 3 works stably under Wine with no change to Far3 itself. Every fix goes into
Wine DLLs (through the [dllmgr](https://github.com/unxed/dllmgr) catalog) or into patches over
DLLs that cannot be replaced.

Open: which problems Far3 hits under current Wine. The console side of Wine may involve DLLs that
cannot be replaced, in which case dllmgr patches (concept section 16) are needed.

## Photoshop trial (possible, not planned)

This could be tried, but it is not planned work: a native Linux port of Affinity is being made
([opennet, news 66605](https://www.opennet.ru/opennews/art.shtml?num=66605)), so an alternative
will soon exist anyway.

If it is tried: several agents work in parallel during the trial period, which limits the time;
prepare the list of areas and scenarios, the split between agents and the reproducers before the
trial starts. Open: installation (the installer and Creative Cloud) under Wine.

## The final showcase (to be chosen)

A showcase is more useful for a program that has no alternative on Linux and none in sight. The
program is to be chosen.

Candidates exclude tax and defense software. Prefer electronic identification software.

Candidates (their state under Wine is not checked yet):

- **Car diagnostics and device firmware tools (for example VCDS).** Usually no alternative;
  they need a USB adapter, so they cannot run in CI.
- **Narrow engineering and scientific software tied to particular equipment or a particular
  industry.** Which programs matter depends on the audience.
