---
name: fix-it-in-wine
description: Fixes a Windows program that misbehaves under Wine on the user's Linux machine. Finds which Wine DLL is at fault, finds the matching WineHQ Bugzilla ticket, builds that one DLL from Wine sources (with the ticket's patch or a small fix), enables it for that program only in one prefix with a one-step undo, and prepares an upstream bug report. Use when the user says a Windows program under Wine shows wrong drawing, crashes, misses controls or behaves differently than on Windows, and wants it fixed.
---

# fix-it-in-wine

The tools are in `tools/` next to this file. They need only Python 3 standard library. `tools/build_one_dll.sh` needs the build packages. Run them by their path in this skill's directory.

## When NOT to use

- The problem is in the Linux system, not in a Windows program (drivers, desktop, audio server).
- DRM, copy protection or anti-cheat: report only, never bypass.
- Kernel drivers (`.sys`) and services that need them.
- GPU driver or Vulkan/OpenGL problems (Wine's graphics stack and the drivers are out of scope).
- The user wants a different Wine version installed: this skill never changes the system Wine.

## Evaluation signals

The job is done only when all of these hold:

- the digest shows the fixed DLL as `native` from the slot path (step 7);
- the user confirms by eye that the problem is gone;
- `tools/override.py status` lists the change as `ok`, and the user has the exact undo command;
- the report text exists and passed the self-check (step 10), or the user declined a report.

## Rules

1. Fail fast. If data is missing, stop and ask the user. Never guess a program path, a prefix, a Wine version or a symptom.
2. Visual symptoms are confirmed by the user. Ask the user to look and to say what they see. Do not decide yourself that a picture is correct.
3. Every change is reversible and limited to one program in one prefix. Use `tools/override.py` only. Do not edit prefix files by hand.
4. Never modify the system Wine installation. Do not install, remove or patch Wine packages. Builds go to the work directory (`~/.cache/fix-it-in-wine`, or `FIW_WORK`).
5. Never post anything to the internet without the user's explicit yes: not a new bug, not a comment. Show the exact text first. Wait for the answer.
6. Clean room, following Wine's [Clean Room Guidelines](https://gitlab.winehq.org/wine/wine/-/wikis/Clean-Room-Guidelines). Study Windows only as a black box: test programs that call the API and check results, run on Windows. Never disassemble Microsoft code, examine its debug symbols, trace native Microsoft components with `+relay`, or write tests that dump internal tables. Never read Microsoft source code (leaked or "public") or ReactOS source code. Allowed sources: Microsoft documentation, Wine sources and tests, behaviour you observe.
7. Keep logs out of the context. Read the digest. Open a full log only to answer one specific question, and read only the needed lines (use `grep`).
8. If a step fails with an unexpected error, report the exact message to the user. Do not work around it silently.
9. Code you write is not offered to Wine. Wine's guidelines forbid LLM-generated code. Your patches, reproducers and tests stay on the user's machine and in the [dllmgr catalog](https://github.com/unxed/dllmgr/tree/main/catalog). Wine gets text: the behaviour, the change in words, and how it was checked (step 10).

## Workflow

### 1. Understand the problem

Ask the user, and stop until you have all of it:

- program name and version;
- full path of the `.exe` that is started;
- the Wine prefix (`WINEPREFIX`; ask if it is not the default `~/.wine`);
- steps that show the problem, and what is expected instead;
- output of `wine --version`.

Preflight, before any run:

- the prefix exists and is initialised: `PREFIX/system.reg` is present (if not, the user has never started a program in it — ask);
- prefix architecture: the line `#arch=win32` or `#arch=win64` in `PREFIX/system.reg`;
- program architecture: `python3 -c "import sys; sys.path.insert(0, 'tools'); import pe_unmark; print(pe_unmark.pe_machine(open(sys.argv[1], 'rb').read()))" EXE.exe` (run from this skill's directory);
- if the program needs .NET or Mono, it is installed in the prefix (ask the user how they installed it).

### 1a. Look for a ready fix

Before any run, search the [dllmgr catalog](https://github.com/unxed/dllmgr/tree/main/catalog) of fixes (one entry per bug):

```
tools/catalog.py search --program NAME.exe
tools/catalog.py search --dll comctl32 toolbar
tools/catalog.py show winehq-59609
```

If an entry matches the program and the symptom, read it with `show`. It gives the bug, the DLLs, the patch, how to build it and, when present, prebuilt files and a one-step apply. Tell the user which entry it is. Then use it: build with the entry's patch (step 5) or take its prebuilt files (check the sha256), enable (step 6), verify (step 7). If nothing matches, go on with step 2.

### 2. Baseline digest

Run the program once with the default preset and a timeout:

```
tools/wineprobe.py run --prefix PREFIX --timeout 60 -- EXE.exe
```

Ask the user to do the steps that show the problem while it runs, then to close the program. Read the digest. The last line gives the full log path. A digest of an existing log:

```
tools/wineprobe.py digest LOG --dll comctl32 --dll user32
```

Keep the digest. You will compare it with later runs.

### 3. Find the DLL

Use the symptom to choose candidates. The table is a starting point, not a proof.

| Symptom | Candidate DLLs |
| --- | --- |
| Buttons, lists, toolbars, tree views, tabs, scroll bars drawn or behaving wrongly | comctl32 (v5 and v6 are different modules in Wine 11) |
| Themed (visual style) drawing wrong | uxtheme, comctl32 |
| Text drawing, fonts, text measuring | gdi32, gdiplus, dwrite, usp10 |
| Image decoding or saving | windowscodecs, gdiplus |
| Common dialogs: open, save, print | comdlg32 |
| Shell: file icons, folders, drag and drop, shortcuts | shell32, shlwapi, ole32 |
| Audio, video playback | winmm, dsound, quartz, mfplat |
| HTML or web controls | mshtml, ieframe |
| Network | winhttp, wininet, ws2_32 |
| Database access | odbc32, oledb32 |
| Missing import, load failure | the DLL named in the digest under `missing imports` |

Narrow it down:

1. Run again with channels for the candidate. Example:

   ```
   tools/wineprobe.py run --prefix PREFIX --preset channels:listview,toolbar --dll comctl32 -- EXE.exe
   ```

   For a crash use `--preset crash`.
2. Check from where the DLL is loaded. The digest line `dll comctl32: native|builtin <path>` shows it. If the path is under `winsxs`, the program uses the side-by-side (v6) copy. Note the path.
3. Release-level bisect. Build the candidate DLL from another tag (step 5), enable it (step 6), run the check (step 7). If the behaviour changes between two releases, the cause is in the commits between them. Compare the tags, then narrow with `git log` and `git bisect` on `dlls/<dll>` in the source tree under `~/.cache/fix-it-in-wine/src/<ref>` (build one commit at a time with `tools/build_one_dll.sh`).

If you cannot name one DLL with evidence, stop and tell the user what you know.

### 4. Find the ticket

```
tools/winebugs.py search comctl32 toolbar program-name
tools/winebugs.py show 12345 --comments 5
tools/winebugs.py attachments 12345
tools/winebugs.py get-attachment 67890 -o /tmp/fix.patch
```

Search by program name, then by DLL and symptom words. Read the candidates with `show`. Look for a patch (`attachments` marks patches with `[patch]`; obsolete ones are hidden unless you pass `--all`) and for a merge request link in the comments. If a ticket matches, tell the user the number and the summary. If nothing matches, say so. Attachment download is plain Bugzilla 5 REST and is not confirmed on WineHQ yet: if it fails, report the error and use the link in the ticket.

### 5. Build the DLL

```
tools/build_one_dll.sh REF DLL [DLL...]
```

`REF` is a tag (`wine-11.0`), a branch or a commit.

- For a minimal change, use the tag of the user's Wine version (from `wine --version`).
- To test whether a newer release fixes the bug, use a newer tag.

If a build package is missing, the script prints the install command and exits with 2. Show that command to the user. Do not install packages yourself without the user's yes.

The script prints the built files. The source tree is `~/.cache/fix-it-in-wine/src/REF`. To apply a ticket patch:

```
git -C ~/.cache/fix-it-in-wine/src/REF apply /tmp/fix.patch
tools/build_one_dll.sh REF DLL
```

Only changed files are rebuilt. If `git apply` fails, the patch does not fit this tag. Try the tag the patch was made for, or report it.

For comctl32 in Wine 11 there are two modules: `comctl32` and `comctl32_v6`. Build the one the program loads (step 3). Build both if unsure.

### 6. Enable it for this program

Use the 32-bit build (`i386-windows`) for a 32-bit program, the 64-bit one (`x86_64-windows`) for a 64-bit program.

```
tools/override.py apply --prefix PREFIX --exe NAME.exe --dll BUILT.dll
```

If the digest showed the DLL loaded from winsxs, use the side-by-side slot, and give the name the program expects:

```
tools/override.py apply --prefix PREFIX --exe NAME.exe --dll BUILT.dll --name comctl32.dll --slot 'sxs:x86_microsoft.windows.common-controls_6595b64144ccf1df_6.*'
```

Not verified yet: that Wine 9 loads Wine 11's `comctl32_v6.dll` placed in winsxs under the name `comctl32.dll`. Step 7 shows whether it worked.

The glob must match exactly one directory under `drive_c/windows/winsxs/`. If the tool reports several or no matches, choose a narrower glob from the listed directories.

The tool prints the exact undo command. Save it. Check the state at any time:

```
tools/override.py status --prefix PREFIX
```

Undo:

```
tools/override.py undo --prefix PREFIX --exe NAME.exe --name comctl32
```

### 7. Verify

Run the program with the same preset as the baseline:

```
tools/wineprobe.py run --prefix PREFIX --preset load --dll comctl32 -- EXE.exe
```

The digest must show `dll comctl32: native <path in the slot>`. If it shows `builtin`, the DLL is not in use: check the slot, the name and the architecture, or undo. Then ask the user to repeat the steps and say, by eye, whether the problem is gone.

- Fixed: go to step 9.
- Not fixed, or worse: run the undo command, or iterate (another tag, another patch, another DLL). Do not leave a failed change in place.

### 8. Order of fix methods

Use the first that works:

1. A fix from the ticket: apply the ticket's patch to the source tree, build, enable, verify.
2. A small fix in Wine's C code, on the tag of the user's version. Write the smallest change that fixes the behaviour. Base it on Microsoft documentation and Wine tests, not on Microsoft binaries.
3. A patch over a DLL that cannot be replaced. This needs dllmgr ([concept](https://github.com/unxed/dllmgr/blob/main/docs/concept.md)). It does not exist yet: do not try.
4. A rewrite of the module in Bp. Rare. Only when the Wine module does not fit the program by design. Wine will not accept this code, so the upstream report stays text only.

Not fixed by this skill (report only): wineserver, graphics and drivers, timings, DRM and anti-cheat.

### 8a. DLLs that cannot be replaced

These cannot be replaced with the tools above: DLLs that have a unix part, and core DLLs: `ntdll`, `kernel32`, `kernelbase`, `user32`, `gdi32`, `win32u`, `winex11.drv`. A DLL has a unix part if the Wine installation has a matching `.so` next to its PE modules, for example `ls /usr/lib/*/wine/*-unix/DLL.so /usr/lib/wine/*-unix/DLL.so /opt/wine*/lib/wine/*-unix/DLL.so 2>/dev/null` prints a file. Do not run `override.py` for them. Identify the cause, write the report (step 10) and tell the user that a local fix is not possible yet.

### 9. Minimal reproducer (when you write your own fix or a report)

Write a small C program (mingw) that shows the bug without the application: create the control, send the message, print the result, return a non-zero exit code on the bug. Run it before and after the fix. It is the proof of the bug and the base of the test in the report.

### 10. Report

Write the report using `templates/bug-report.md`. Fill every section.

Self-check: give a cheaper subagent only the report text and the Wine source tree (no other context, no access to your notes). It must write a patch from the text, the patch must build, and the reproducer must pass. If it fails, the report lacks precision: find what was missing, fix the text, check again.

Show the final text to the user. Say whether it is a new bug or a comment in ticket N.

Gate before posting. A test that reproduces the behaviour described in the ticket fails on the unmodified Wine build and passes with only the proposed change, and the change was also checked by eye in the real application (the user confirms). A synthetic probe alone, or a build with several changes, does not pass the gate. Record the program version, Wine build, architecture, display setup, the exact command and the results.

Post only after the user's explicit yes. Posting goes through the user's own Bugzilla login in the agent's browser (the user logs in at https://bugs.winehq.org; you must not ask for the password). Do not attach, paste or link code you wrote (rule 9): describe it in words only. A patch written by a person, such as one already in the ticket, may be referenced as usual. State in the text that it was prepared with an AI agent.

### 11. Finish

Tell the user:

- what was changed: the program, the prefix, the DLL, the slot path, the Wine tag;
- that nothing else was changed: other programs and the system Wine are untouched;
- the exact undo command;
- that the change stays after a Wine update and is not updated with it. After a Wine update, run `tools/override.py status` and check again.

## Self-improvement

When your experience shows how to make this skill better, open a pull request to https://github.com/unxed/fix-it-in-wine right away. Cases:

- a step had to be invented;
- a preset or a tool was missing;
- an instruction was wrong;
- a new kind of problem appeared.

The PR says what happened, what to change, and on which case it showed up. Write generalised experience only: no user data, no paths, no logs, no program names unless they are public and needed.

Opening a PR is a post to the internet. For a PR to the skill's own repository this is part of the skill, but if the PR text contains anything from the user's machine, remove it first.

If a PR is not possible (no GitHub access), save the proposal to `~/.cache/fix-it-in-wine/proposals/<date>.md` (create the directory) and tell the user where it is.
