# fix-it-in-wine: concept

fix-it-in-wine is a skill for AI agents. The user describes to the agent a Windows program that misbehaves under Wine. The agent finds the cause in one DLL, finds or writes a fix, builds that DLL, enables it for that program only, and prepares an upstream report.

The skill grew out of the [dllmgr](https://github.com/unxed/dllmgr/blob/main/docs/concept.md) design. It depends on three primitives that dllmgr provides. Until dllmgr exists, small stand-in tools in this repository cover them (see "Proof of concept (now)").

## 1. Realism

"Any application" is not a realistic goal. The realistic class of tasks:

- regressions;
- bugs in leaf DLLs;
- some deeper bugs, through patches over DLLs that cannot be replaced.

For everything else the result is a high-quality report.

This is cheap because of three primitives:

1. Bisect by one DLL between Wine releases, without installing Wine.
2. Build one DLL from the sources of an exact version.
3. Apply, undo and verify for one program.

## 2. Target scenario

In FastStone Image Viewer the top preview bar does not show all previews (bugs.winehq.org 59251). The user describes the problem to their agent and gives it a link to the skill. The user does not look at the Wine bug tracker. The agent:

1. determines which DLL has the problem;
2. looks for a matching ticket;
3. builds that DLL on the user's system;
4. fixes it, or applies the fix from the ticket;
5. enables the fixed DLL in the user's Wine;
6. offers to send a report: a new bug, or a comment in an existing ticket, describing how to fix it, based on the experience of this run.

The user only has to log in to WineHQ Bugzilla, confirm the result by eye, and allow sending.

## 3. Pipeline

1. **Reproduce and narrow down.** The user describes the symptom. The user also confirms visual results. The skill asks, it does not guess. Data is collected by `dllmgr diag` ([debug-data collection](https://github.com/unxed/dllmgr/blob/main/docs/concept.md)). The skill reads the digest and asks for full logs only when needed.
2. **Find the module.** Bisect by release through dllmgr: substitute the DLL from a newer or older Wine. Where the behaviour changes, there is a regression or a fix, with release precision. Then `git bisect` over the commits that touched `dlls/<dll>`, with local builds. One DLL is rebuilt, which takes minutes.

   In parallel, search for a ticket. The WineHQ Bugzilla REST API answers without login. Checked on 2026-11-06: `https://bugs.winehq.org/rest/bug?quicksearch=FastStone&include_fields=id,summary,status` found 5129, 43490, 59251, 59609. From the found tickets the skill takes symptoms, traces and ready patches: attachments or links to merge requests in Wine GitLab.
3. **Minimal reproducer.** A tiny C program (mingw) reproduces the bug without the application: create a control, send a message, print the result. It runs under Xvfb, and the exit code is the verdict. It is at once the proof of the bug, the test of the fix, and the prose description of a future Wine test.
4. **Fix.** The methods, in order of preference:
   1. A ready fix from the ticket: `git apply` to the sources of the user's version, build one DLL, enable it for the program, verify.
   2. A small C fix in the Wine sources of the version the user has (or master, if the import check passes), by the same route. A small change is also the easiest for a Wine developer to reimplement from the report.
   3. The bug is deeper (unix part, user32/win32u): a **patch** over a DLL that cannot be replaced. See [patches over DLLs that cannot be replaced](https://github.com/unxed/dllmgr/blob/main/docs/concept.md). The patch intercepts the broken function and supplies the correct behaviour. It is installed through dllmgr under the same rule.
   4. Rewrite the module from scratch in Bp (as cc580 was). It builds faster, and there is less to think about memory. Use it only when the Wine module does not fit the program by design, or another reference behaviour is needed. Wine will not accept Bp code, so the report stays textual.

   Not fixed (wineserver, graphics and drivers, timings, DRM and anti-cheat): report only.
5. **Upstream report.** A text for bugs.winehq.org: a new bug or a comment in the found ticket. Wine does not accept LLM-generated code, so the report carries no code the agent wrote: the problem, the Windows behaviour, the fix in words and the results. The patch stays in the [dllmgr catalog](https://github.com/unxed/dllmgr/tree/main/catalog); the prose of its fix entry has the same parts as the report (dllmgr decisions D16, D17). Before posting, the gate in step 10 of `SKILL.md` must pass. The agent prepares the text and sends it only after the user says yes. Login: the user logs in to Bugzilla in the agent's browser, or creates an API key once in the profile settings (then the agent writes through REST without driving a browser). The template (`templates/bug-report.md`):
   - program and its version, Wine versions, regression commit;
   - symptom;
   - minimal reproducer;
   - cause: file, function, line at commit X; what happens and what should happen, with links to Microsoft documentation;
   - fix in steps, with edge cases;
   - a test for `dlls/<dll>/tests` in words: setup, actions, expected values;
   - how it was checked.

   Completion criterion: **the report is checked by doing**. A cheaper model, as a subagent, gets only the report text and the Wine tree, writes a patch from it, the patch builds, and the reproducer passes. If it does not pass, the report is not precise enough.
6. **No Microsoft code.** Windows is studied only as a black box: test programs run on Windows. Never disassemble Microsoft DLLs, examine their debug symbols, `+relay` native Microsoft components or use Microsoft or ReactOS sources, leaked or not. The sources are Microsoft documentation, Wine tests and observed behaviour. These are requirements of Wine's [Clean Room Guidelines](https://gitlab.winehq.org/wine/wine/-/wikis/Clean-Room-Guidelines), which also forbid LLM-generated code.
7. **Self-improvement.** When experience shows the agent how to make the skill better, it opens a pull request to [unxed/fix-it-in-wine](https://github.com/unxed/fix-it-in-wine) right away: a change to the skill, the presets or the tools. Examples: a step had to be invented; a preset was missing; an instruction was wrong; a new kind of problem appeared. The PR says what happened, what to change, and on which case it showed up. Only generalised experience: no data, paths or logs from the user's machine. If a PR cannot be opened (no GitHub access), the agent saves the proposal to a file and tells the user.

## 4. Where it runs

A local agent on the user's machine (the application, Wine and a display are needed). A cloud sandbox is for building and static analysis only. Dependencies come from the distribution repository: mingw-w64 and the packages for a minimal Wine configure. Disk space: one Wine build tree. The sources of the user's exact version come from `apt source wine`, so the Debian patches are included (deb-src is required).

## 5. Building one DLL without building all of Wine

Checked against `tools/makedep.c` of the `wine-9.0` tag. makedep generates one common Makefile. Each module has its own target `dlls/<dll>/all`. The build tools (winebuild, widl, wrc) have the target `__tooldeps__`. `make` on these targets builds only the dependency closure of the module:

- the tools;
- the headers generated from IDL;
- the import libraries of the dependencies, from their `.spec` files through `winebuild --implib`;
- the module itself.

Recipe (exact flags are refined by the blocker check):

```
./configure --enable-archs=i386,x86_64 --without-x --without-freetype   # + other --without-*
make __tooldeps__ dlls/comctl32/all
```

`--enable-archs` builds the mingw PE modules. 32-bit system libraries are not needed. The result is an ordinary PE file, usable by classic Wine 9 as well.

**If the Wine build system cannot do this, we learn to:** write our own minimal single-DLL builder. It takes the module's `Makefile.in` (`MODULE`, `IMPORTS`, `DELAYIMPORTS`, `EXTRADEFS`, `PARENTSRC`, `SOURCES`) and the `.spec` files of the imported DLLs. The tools come from Wine in the same tree: winebuild, widl and wrc are built separately with the host compiler.

### 5.1 Blocker check

At the start, only a check for blockers of principle. Speed and disk space are not blockers and are not optimised at the start.

- **B1.** configure passes on a clean system: packages only from the distribution repository (mingw-w64, gcc, flex, bison), optional libraries disabled.
- **B2.** `make __tooldeps__ dlls/<dll>/all` builds the PE module and does not pull in the build of most of the tree (count the built targets).
- **B3.** The built DLL, after the builtin mark is cleared, is loaded as native by the user's system Wine (`verify`).
- **B4.** The sources of the user's exact version are available (`apt source wine` or an upstream tag).

If a blocker is found:

- B1 or B2: write our own builder (see above).
- B3: investigate in dllmgr, not in the build.
- B4: the upstream tag, plus a comparison with the distribution patches that touch this DLL.

### 5.2 Result of the check

Date 2026-11-06. Sandbox on Ubuntu 24.04, the same base as Mint 22. Tag `wine-11.0`. Modules comctl32 and comctl32_v6.

- **B1: no blocker.** Only repository packages are needed: gcc, make, bison, flex, gcc-mingw-w64-i686, gcc-mingw-w64-x86-64. `configure --enable-archs=i386,x86_64 --without-x --without-freetype` takes 19 s. Warnings concern only gettext, gnutls and sound.
- **B2: no blocker.** Our own builder is not needed.
  - `make -j4 __tooldeps__` takes 9 s. `make -j4 dlls/comctl32/all dlls/comctl32_v6/all` takes 39 s, for both architectures.
  - 253 object files were built: comctl32 56, comctl32_v6 70, winecrt0 30, ucrtbase 16, uuid 4, tools 73.
  - Rebuild after a change to one file: 4 s.
  - Disk: sources 389 MB, build directory 164 MB.
- **B3: checked partly.**
  - The built DLLs carry the builtin mark. It must be cleared (see F1).
  - All regular imports of the i386 builds (307 for comctl32, 384 for comctl32_v6) exist in the exports of Wine 9.0 from Ubuntu noble (package `libwine` 9.0~repack-4build3, i386).
  - Delay imports (oleacc, winmm, uxtheme) were not checked statically: in the Wine build the delay-import directory in the PE is empty. Where the descriptors lie is to be found when the `check` command is written.
  - Loading in a live Wine 9 is checked by spike S0.
- **B4: no blocker for an upstream tag.** A shallow clone of `wine-11.0` from the mirror `wine-mirror/wine` takes 8 s. `apt source wine` for the user's exact version was not checked.

## 6. Checked facts about Wine

Checked against the sources of the tags `wine-9.0` and `wine-11.0`.

- **F1. The builtin mark.** In Wine's built-in DLLs, right after `IMAGE_DOS_HEADER` (offset 0x40), there are 32 bytes `"Wine builtin DLL"`. What the loader does with such a file (`dlls/ntdll/unix/loader.c`, `load_builtin()`): with load order `native` the file is "not found"; with any other order it loads **its own** built-in DLL from the installation directory. So a DLL from another Wine version is ignored unless it is changed. The solution: zero these 32 bytes ("clear the mark"). Files with the mark `"Wine placeholder DLL"` are empty stubs without code; they are not accepted.
- **F2. Load order** (`dlls/ntdll/unix/loadorder.c`: `get_load_order`, `get_load_order_value`). For each form of the name in turn, Wine checks `WINEDLLOVERRIDES`, then `HKCU\Software\Wine\AppDefaults\<exe>\DllOverrides`, then `HKCU\Software\Wine\DllOverrides`. The name forms: the full path without extension (for files from the system directory, just the name), then `*name`, then `name`. If there is no override (`LO_DEFAULT`), the built-in DLL wins even when a native file is found; the exception is a built-in DLL with the PREFER_NATIVE flag. Two consequences: without an explicit override our file is not loaded, and other programs do not pick it up.
- **F3.** With order `native,builtin`, a file without the mark is loaded as native, and an untouched file with the mark still gives Wine's built-in DLL (`load_builtin` turns the order into `LO_BUILTIN_NATIVE`). So always write `native,builtin`, not `native`.
- **F4.** When Wine is updated, wineboot (`dlls/setupapi/fakedll.c`: `create_dest_file`, `is_fake_dll`) does not overwrite files that have neither the builtin nor the placeholder mark. So our file survives a Wine update and keeps being used. A change of the Wine version must be tracked.
- **F5. comctl32 in Wine 9 and 11.** In Wine 9 one comctl32 serves both v5 and v6 (v6 through winsxs). In Wine 11 these are two modules: `comctl32.dll` and `comctl32_v6.dll` (`dlls/comctl32_v6`, installed into system32). The imports changed too: Wine 11 added `oleaut32` and a delayed `oleacc`. So "comctl32 from Wine 11" has two variants, and for Wine 9 the v6 variant is placed in a winsxs slot under the name `comctl32.dll`. What exactly FastStone needs is to be shown by spike S0.
- **F6. Log lines** (`dlls/ntdll/loader.c`): `trace:loaddll ... Loaded <path> at <address>: native|builtin`. A missing import is a WARN in the `module` channel: `No implementation for X.Y imported from Z, setting to ...`. `WINEDEBUG=+loaddll,warn+module` is needed. A missing import does not stop loading; the crash comes at the call.
- **F7.** In the WineHQ pool `https://dl.winehq.org/wine-builds/ubuntu/pool/main/w/wine/` there are i386 packages of Wine 11 for noble: `wine-stable-i386_11.0.0.0~noble-1_i386.deb`, `wine-devel-i386_11.21~noble-1_i386.deb` (state on 2026-11-06). The path inside a package is found with `find` on `*/i386-windows/<dll>.dll`, without hard-coding the prefix.

Hypotheses that spike S0 checks:

- **H1.** comctl32 from Wine 11 with the mark cleared is loaded in Wine 9 as native. If "No implementation" lines appear, they show which functions are missing.
- **H2.** FastStone loads comctl32 from system (v5) or from winsxs (v6). Which one is to be found.
- **H3.** The FastStone bugs in question are really fixed in Wine 11. In the dialog of 59609 the bug also reproduced on 11.12, so not everything is fixed.
- **H4.** `comctl32_v6.dll` placed in winsxs under the name `comctl32.dll` works.

## 7. Iterations

After iterations 1-2 of dllmgr:

- **S1: diagnostician.** Symptom, traces, bisect by release on prepared variants, a draft report. Step 7 of the pipeline (a PR with skill improvements) is present from the first release.
- **S2: building one DLL.**
  - The first step is the blocker check B1-B4. If B1 or B2 is found, write our own builder.
  - Then `wine-build-dll <dll> <tag|commit>` (with a configure cache), a reproducer template, and a run under Xvfb.
  - Ticket search through the Bugzilla REST API.
- **S3:** the fix loop, the report template, and the check of the report by a cheaper model.
- **S4:** the skill writes patches per [patches over DLLs that cannot be replaced](https://github.com/unxed/dllmgr/blob/main/docs/concept.md) (after dllmgr iteration 6).
- **S5:** fixes in the index as build descriptions (base tag plus patch). The index CI builds them itself. Binaries built by an AI are not accepted.

## 8. Proof of concept (now)

dllmgr does not exist yet. The repository contains tools that cover the first iterations. Each is a Python 3 standard-library script, except the build script.

| Tool | Purpose |
| --- | --- |
| `tools/pe_unmark.py` | Clears the "Wine builtin DLL" mark (F1) of a PE file. Used by `override.py`. |
| `tools/build_one_dll.sh` | Builds one or more DLLs from a Wine tag, branch or commit, without building all of Wine (section 5). Needs the build packages. |
| `tools/wineprobe.py` | Runs a program with a debug preset and prints a short digest of the log: which DLLs were loaded and as what, missing imports, exceptions, errors, most frequent fixmes. |
| `tools/winebugs.py` | A read-only client of the WineHQ Bugzilla REST API: search, show a bug, list and download attachments. |
| `tools/catalog.py` | A read-only search in the [dllmgr catalog](https://github.com/unxed/dllmgr/tree/main/catalog) of fixes (one entry per bug): by program, DLL, bug or words. The skill runs it before building anything. |
| `tools/override.py` | Enables one DLL for one program in one prefix, reversibly: `apply`, `undo`, `status`. |

`tools/override.py` and `tools/wineprobe.py` are stand-ins. When dllmgr exists, it replaces them: `dllmgr diag` replaces `wineprobe.py`, and dllmgr's apply and undo replace `override.py`. Whether `pe_unmark.py`, `build_one_dll.sh` and `winebugs.py` stay is decided when dllmgr is written.

The skill (`SKILL.md`) uses only these tools. Patches over DLLs that cannot be replaced are not possible yet: for such bugs the skill produces a report only.

## 9. Open questions

- Which comctl32 variant FastStone needs (spike S0, F5, H2).
- Whether the delay imports of a DLL from another Wine version are resolved in the user's Wine (B3).
- Whether `apt source wine` gives the user's exact version (B4).
- The attachment download of the WineHQ REST API is standard Bugzilla 5 and is not checked on WineHQ yet.
