# Making the construction more efficient — ideas

Scope: fix-it-in-wine (the entry point for people), dllmgr, Marwin, cc580, Bp.
Optimised first for the skill. Status of every idea: **proposal**. Items marked
**[unverified]** rest on behaviour I have not checked in this session.

The skill spends three kinds of resources, in this order of cost:

1. **Human round trips.** Waiting for the user to reproduce, look at the screen and answer.
2. **Tokens.** Reading logs, bug threads and Wine sources (listview.c alone is ~11k lines).
3. **Machine time.** Small already: configure 19 s, one DLL 39 s, rebuild after one change 4 s.

So the main lever is removing the human from the inner loop. Next comes reading less;
build speed is already good enough.

---

## 1. Do not solve the same problem twice

### 1.1 Known-fixes lookup as step 0 of the skill
- **What.** Before any investigation, look up the program in the dllmgr catalog. Key:
  exe name, version resource and sha256; also the symptom keywords. Variants and patches
  already carry `apps` and `fixes` fields (see the dllmgr concept). When a hit exists, the
  whole session is "apply variant X for FSViewer.exe, verify, done".
- **Why.** Most users of one program hit the same bug. The second and later users should
  pay seconds, not an investigation.
- **Cost.** Small: one catalog query + a manifest field `symptoms = [...]`.
- **Risk.** A wrong match → mitigated by `verify` and by the user's check.
- **Repo.** dllmgr (catalog fields), fix-it-in-wine (step 0).

### 1.2 Investigation notes that survive the session
- **What.** `~/.cache/fix-it-in-wine/notes/<exe>-<version>.md` holds what was tried, which
  DLL, which bug, which build tree. A new session reads the notes first. The generalised
  part goes upstream through the self-improvement PR.
- **Why.** Sessions end and contexts overflow; re-deriving the same facts costs tokens.
- **Cost.** Tiny. **Repo.** fix-it-in-wine.

### 1.3 Continuous watcher in CI
- **What.** Every fix becomes a *repro pack* (§3.4). A nightly CI job runs every pack against
  the newest Wine release, with and without the override:
  - builtin now passes → dllmgr marks the override obsolete, and `status` tells users;
  - a new Wine fails a pack → an alert.
- **Why.** Overrides are removed when Wine catches up; upstream regressions are seen early.
  No tokens, no humans.
- **Cost.** Medium, after repro packs exist. **Repo.** dllmgr (CI, catalog), packs in fix-it-in-wine.

---

## 2. Fewer human round trips

### 2.1 One structured interview at the start
- **What.** The skill collects everything in one batch:
  - the program, its version, the exe path and the prefix;
  - the symptom, what was expected, and the steps to reproduce;
  - whether the installer can be run silently;
  - whether the agent may work in a shadow prefix (§2.2) without asking;
  - test data: the user's folder, or generated files.
- **Why.** Every extra question is minutes or hours of latency.
- **Cost.** Tiny. **Repo.** fix-it-in-wine (SKILL.md).

### 2.2 Shadow prefix
- **What.** All experiments run in a throwaway copy of the user's prefix:
  `cp --reflink=auto -a`; instant on btrfs/xfs, a plain copy elsewhere; fuse-overlayfs is an
  option without root **[unverified on Mint defaults]**. Alternatively a fresh prefix
  (`wineboot -i`) with a silent install of the program. Only the confirmed fix is applied to
  the real prefix, through `override.py`/dllmgr.
- **Why.** The agent may break things freely, so it does not need to ask before each experiment.
- **Cost.** Small. **Risk.** Disk space; licences tied to the prefix. **Repo.** fix-it-in-wine, later dllmgr.

### 2.3 Autonomy levels in the config
- **What.**
  - L0 — ask before everything.
  - L1 — free inside the shadow prefix and the work dir.
  - L2 — may also apply and undo overrides in the real prefix.
  - Posting upstream always needs a "yes".
- **Why.** Users who trust the agent stop being interrupted; cautious users keep control.
- **Cost.** Tiny. **Repo.** fix-it-in-wine.

### 2.4 Watching without disturbing
- **What.** The program runs in Xephyr (a nested X server, a window on the user's desktop)
  or in Xvfb (no window at all). The user can glance at it, but the scenario does not steal
  focus.
- **Cost.** Tiny. **Repo.** fix-it-in-wine.

---

## 3. Replace the human's eyes with numbers

The symptom "not all previews are shown" is visual, yet it has an exact numeric form: drawn N
of M items. Getting that number removes the human from verification.

### 3.1 `wintree` — a window/control state dump
- **What.** A small mingw-built exe run inside the same Wine session (same wineserver). It
  dumps the target process's window tree as compact JSON: class, rect, visibility, style and
  text. For known control classes it adds their state:
  - SysListView32: item count, top index, count per page, view mode, item rects;
  - toolbar, tree view, tab and status bar: their main counters.
  Cross-process queries need pointer marshalling (VirtualAllocEx + WriteProcessMemory +
  ReadProcessMemory), the same trick spy tools use **[unverified in Wine, expected to work]**.
- **Why.** Token-cheap, exact, runs headless; it also lets scenarios wait for the right state.
- **Cost.** Medium: 300–500 lines of C. **Repo.** fix-it-in-wine (tool), later dllmgr diag.

### 3.2 In-process observer
- **What.** A patch DLL loaded through dllmgr's entry-DLL mechanism. It subclasses or hooks the
  target control and logs in compact JSONL:
  - the messages the program sends to it, with LVM_* names decoded and the return values;
  - NM_CUSTOMDRAW notifications per item (which items were actually painted).
- **Why.** Gives the drawn N of M directly, and the exact message whose result is wrong. For
  bug 59609 it would show LVM_GETITEMPOSITION results without anyone reading listview.c.
- **Cost.** Medium; it reuses dllmgr patches (I6). **Risk.** Hooks change timing slightly.
- **Repo.** dllmgr (`patches/observer`), used by the skill.
- **Existing option first:** Wine's `+message` channel already prints messages through
  user32's spy code, which decodes many common-control message names. Check it before writing
  a decoder **[unverified: the LVM coverage of spy.c]**.

### 3.3 Screenshots as the last resort
- **What.** Capture the window under Xvfb (`xwd`/`import`), crop and downscale. First a
  perceptual diff (SSIM) against a reference picture — the "fixed" run, or the same scenario
  on Windows (§4.1). Ask a cheap vision model a yes/no question only when the diff is ambiguous.
- **Why.** Covers rendering bugs that §3.1 and §3.2 cannot express in numbers.
- **Cost.** Small. **Repo.** fix-it-in-wine.

### 3.4 Repro pack
- **What.** A self-contained directory that anyone, or CI, can run:
  - program URL + sha256 and the silent-install flags (NSIS `/S`, Inno `/VERYSILENT`;
    **[unverified for the FastStone installer]**);
  - a test-data generator (e.g. 300 small JPEGs, so no private data is involved);
  - a scenario script: xdotool steps synchronised by `wintree` waits, not by sleeps;
  - checks: `wintree`/observer expressions such as `drawn == visible_slots`;
  - expected results, from Windows (§4.1) or from the fixed build.
- **Why.** One artifact serves as proof of the bug, an autonomous test of the fix, evidence
  for the upstream report (link it from the bug), and an input to the watcher (§1.3).
  goWidgets already runs FastStone under Wine in CI (`fsref.yml`), so the pattern is proven
  there.
- **Cost.** Medium. **Repo.** fix-it-in-wine (format + runner), packs may live in dllmgr's catalog.

---

## 4. Ground truth without a human

### 4.1 Windows oracle in GitHub Actions
- **What.** The minimal reproducer (a tiny C program, §15 of the skill concept) is built with
  mingw on Linux. A `workflow_dispatch` job on `windows-latest` runs it and returns its
  output; the skill compares that output with the Wine run. The same runner can run a repro
  pack for the whole program **[unverified: GUI programs and screenshots on hosted Windows
  runners; console output is safe]**.
- **Why.** Objective expected values in about two minutes, free for public repos. This is
  black-box observation of Windows behaviour, the same way Wine's own tests are validated, so
  it stays clean-room.
- **Cost.** Small for console reproducers; medium for GUI. **Risk.** Runner OS (Server 2022)
  differs from desktop Windows. **Repo.** fix-it-in-wine (workflow, invoked with the user's `gh`).

### 4.2 Wine's conformance tests as a regression gate
- **What.** Build `dlls/<dll>/tests` with the same one-target trick (target name **[unverified]**).
  Run the relevant test file (e.g. `comctl32_test.exe listview`) under the user's Wine,
  before and after the fix. A new failure = the fix broke something.
- **Why.** Cheap protection; it also tells the agent which test file to extend in the report.
- **Cost.** Small. **Repo.** fix-it-in-wine.

### 4.3 Same probe on both systems
- **What.** The observer DLL (§3.2) is a plain PE, so it also runs on Windows. Run the same
  scenario with the same observer on Windows and under Wine. The first difference in the
  message/result sequence is usually the root cause.
- **Why.** Turns "read the code and think" into "diff two short logs".
- **Cost.** Medium once §3.2 and §4.1 exist. **Repo.** dllmgr + fix-it-in-wine.

---

## 5. Shorter inner loop

- **5.1 Printf debugging is the default.** Add `ERR("dbg ...")` lines to the Wine source,
  rebuild (4 s), rerun, and read only the `errors:` part of the wineprobe digest. Document it
  in SKILL.md as the first tool, before any debugger.
- **5.2 Keep wineserver alive.** `wineserver -p` between runs saves its start-up on every run
  **[unverified: how much time it saves]**.
- **5.3 Scripted breakpoints.** Our builds carry debug info (`-g`; 4 MB DLLs), so gdb through
  `winedbg --gdb` with a batch script — break in the handler, print locals, continue — is
  possible without editing code **[unverified: gdb + mingw symbols under Wine 9]**.
- **5.4 Release-level bisect without compiling.** dllmgr extracts the DLL from each WineHQ
  package. A binary search over ~40 releases is about 6 runs. With a repro pack it runs
  unattended. Commit-level bisect inside the found range then uses `build_one_dll.sh <commit>`
  **[unverified: old commits may need other configure flags]**.
- **5.5 Fix on two bases at once.** Build from the user's exact version (minimal change for
  local use) and keep the same patch rebased on master (for the upstream text). The skill
  does both in two build trees.

---

## 6. Fewer tokens

- **6.1 Wine source navigator.** A tool that prints one function body, finds `case LVM_X:` and
  its handler, shows `git log -L` for that function, and lists the tests that mention the
  message. The agent reads about 80 lines instead of 11k.
  - **Cost.** Small: ctags or a simple brace matcher.
  - **Repo.** fix-it-in-wine.
- **6.2 Precomputed maps per DLL.** Message → handler function, debug channel → source file,
  symptom words → candidate DLLs. Generated from the Wine tree once per tag and cached.
- **6.3 Model routing in the skill.** Mechanical steps go to a cheap model or subagent: bug
  triage ("read these 20 tickets, return the relevant ids with one line each"), build and apply
  loops, report self-check. Root-cause reasoning stays with the strong model. Write the routing
  into SKILL.md.
- **6.4 `--json` on every tool.** Machine-readable output for chaining; the plain digest stays
  the default for reading.
- **6.5 Divergence windows.** When comparing two logs, show only ±20 normalised lines (addresses,
  handles and timestamps stripped) around the first difference.

---

## 7. Automatic minimal reproducer

- **What.** Turn the observer log (§3.2) of the real program into a C program that replays the
  same message sequence against a fresh control. Then shrink it with delta debugging (ddmin):
  keep removing messages while the Windows output and the Wine output still differ. The
  result is a minimal reproducer and, with Windows values as `ok()` checks, a ready Wine
  conformance test description.
- **Why.** Removes the most skilled manual step: understanding the program well enough to
  write a reproducer.
- **Cost.** High. Messages with pointer structs (LVITEM, NMHDR…) need per-message marshalling
  tables. Start with scalar-parameter messages of one control class.
- **Risk.** Some bugs depend on timing or painting and will not replay. **Repo.** fix-it-in-wine (research track).

---

## 8. Things the owner may not have planned

- **8.1 Who reviews the self-improvement PRs.** Many users' agents sending PRs need a
  maintainer:
  - a PR template;
  - CI that lints SKILL.md and runs the tool tests;
  - a reviewer — the Lunobot fleet, with its project entry covering fix-it-in-wine;
  - a rule that a PR must cite the concrete case it came from.
- **8.2 Upstream etiquette.** Always comment on an existing ticket rather than open a new one;
  one report per bug per user; reports contain a repro pack link and Windows values. This
  keeps Wine developers' trust, which the whole construction depends on.
- **8.3 cc580 observes itself.** We own the code, so cc580 can write a compact message trace on
  its own (no hooks). On real Windows it can be dropped app-local, and any behaviour difference
  between the program with Microsoft's comctl32 and with cc580 is a cc580 bug, independent of
  Wine. That is a fully automatic development loop for cc580 on a Windows CI runner.
- **8.4 Marwin as an instrumented runtime.** Marwin implements the Win32 API itself, so it can
  log every call with typed arguments at almost no cost — a strace for Win32 console programs.
  Wine's conformance tests run against Marwin for correctness and speed (already planned);
  `dllmgr check --target marwin` gives Marwin's missing-API list.
- **8.5 MCP server wrapper (optional).** Expose the tools as typed MCP tools for any agent.
  This saves prompt text and makes outputs structured, at the price of one more install step.
  Do it after the tool CLIs settle.
- **8.6 Security line.** The skill builds DLLs from source on the user's machine and accepts
  binaries only from the dllmgr catalog with pinned hashes. Write this rule into SKILL.md
  explicitly.

---

## Ranking (value / effort)

| # | Idea | Value | Effort |
|---|------|-------|--------|
| 1 | Known-fixes lookup as step 0 (§1.1) | very high | tiny |
| 2 | One structured interview + autonomy levels (§2.1, §2.3) | high | tiny |
| 3 | Printf loop documented as default; `wineserver -p` (§5.1, §5.2) | high | tiny |
| 4 | Shadow prefix (§2.2) | high | small |
| 5 | Windows oracle for console reproducers (§4.1) | high | small |
| 6 | Wine source navigator + precomputed maps (§6.1, §6.2) | medium-high | small |
| 7 | Model routing in SKILL.md (§6.3) | medium | tiny |
| 8 | Conformance tests as regression gate (§4.2) | medium | small |
| 9 | `wintree` (§3.1) | high | medium |
| 10 | Repro pack + Xvfb runner (§3.4) | high | medium |
| 11 | Release bisect without compiling, unattended (§5.4) | medium-high | medium |
| 12 | Observer DLL; first check `+message` (§3.2) | high | medium |
| 13 | Continuous watcher in CI (§1.3) | high | medium (after 10) |
| 14 | Same probe on Windows and Wine (§4.3) | high | medium (after 5, 12) |
| 15 | Self-improvement PR governance via Lunobot (§8.1) | medium | small |
| 16 | cc580 self-trace + A/B on Windows (§8.3) | medium | medium |
| 17 | Automatic minimal reproducer with ddmin (§7) | very high | high, research |
| 18 | MCP wrapper (§8.5) | low-medium | small, later |
