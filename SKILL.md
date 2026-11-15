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
- if the program needs .NET or Mono, it is installed in the prefix (ask the user how they installed it);
- with a launcher (Bottles, Lutris, Steam, a Flatpak), the system `wine --version` is not the Wine in use. Take the runner from the launcher's bottle or game config, or from `/proc/PID/cmdline` of the running program. Take the Wine, DXVK and GPU variables from `/proc/PID/environ`, filtered by name (never print the whole environment), and put them in a wrapper script used as `FIW_WINE`;
- no process of this prefix is running anywhere. A Flatpak sandbox has a private `/tmp`, so a wineserver started on the host does not see the sandbox's wineserver for the same prefix, and two servers on one prefix can lose or corrupt registry changes. Close the program and its helper processes first. Find them by the runner path or by `WINEPREFIX` in `/proc/PID/environ`; `pkill -f PATTERN` also kills the shell that runs it when the pattern is in its own command line.

### 1a. Look for a ready fix

Before any run, search the [dllmgr catalog](https://github.com/unxed/dllmgr/tree/main/catalog) of fixes (one entry per bug):

```
tools/catalog.py search --program NAME.exe
tools/catalog.py search --dll comctl32 toolbar
tools/catalog.py show winehq-59609
```

If an entry matches the program and the symptom, read it with `show`. It gives the bug, the DLLs, the patch, how to build it and, when present, prebuilt files and a one-step apply. Tell the user which entry it is. Then use it: build with the entry's patch (step 5) or take its prebuilt files (check the sha256), enable (step 6), verify (step 7). If nothing matches, go on with step 2.

If `catalog.py` stops with "the index must be a JSON array of objects", the index is in the format-1 envelope (`{"format": 1, "entries": [...]}`, issue #13). Report that error to the user, then search the `entries` of `index.json` directly.

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

On timeout, `wineprobe.py` kills only the `wine` launcher: the program, its helper processes and the wineserver keep running. Stop them with `wineserver -k` (same `WINEPREFIX`, the wineserver of the same Wine build) before the next run or an `override.py` call.

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
| A GPU-drawn child window (canvas, video, 3D view) shows old content while it updates | win32u (see "Known case" below) |

Narrow it down:

1. Run again with channels for the candidate. Example:

   ```
   tools/wineprobe.py run --prefix PREFIX --preset channels:listview,toolbar --dll comctl32 -- EXE.exe
   ```

   For a crash use `--preset crash`.
2. Check from where the DLL is loaded. The digest line `dll comctl32: native|builtin <path>` shows it. If the path is under `winsxs`, the program uses the side-by-side (v6) copy. Note the path.
3. Release-level bisect. Build the candidate DLL from another tag (step 5), enable it (step 6), run the check (step 7). If the behaviour changes between two releases, the cause is in the commits between them. Compare the tags, then narrow with `git log` and `git bisect` on `dlls/<dll>` in the source tree under `~/.cache/fix-it-in-wine/src/<ref>` (build one commit at a time with `tools/build_one_dll.sh`).
4. An action that silently leaves the old view on screen (no crash) is often cancelled by a stub. In a `--preset crash` log, look for a fixme on the UI thread (a stub returning `E_NOTIMPL`) followed at once by a C++ exception (`code=e06d7363`) from the program's own module: `info[3]` of the exception is the image base of the throwing module, match it with the `loaddll` lines. A handler near the outer frames of the stack (close to the message loop) means the whole action was unwound. That stub is the candidate. Rule out the rendering path first, cheaply: switch off the program's own GPU acceleration; if the symptom stays, the GPU path is not the cause.

Known case: in Wine 10.0-based builds the server keeps a child window out of the parent's window surface only when it has an OpenGL pixel format (`SET_WINPOS_PIXEL_FORMAT`). A child window with Vulkan surfaces (DXVK or vkd3d-proton swapchains) is not excluded, so window-surface flushes paint old pixels over the presented frames whenever other parts of the window redraw; the frames show again when the redraws stop. Upstream changed this in the client-surface rework (for example `7993d8b86cb9`, "win32u: Fix clipping out of vulkan and other process client surfaces"). The fix belongs in win32u, which has a unix part (step 8a). Confirm the case with the pixmap comparison in step 7 before changing anything.

If you cannot name one DLL with evidence, stop and tell the user what you know.

### 4. Find the ticket

```
tools/winebugs.py search comctl32 toolbar program-name
tools/winebugs.py show 12345 --comments 5
tools/winebugs.py attachments 12345
tools/winebugs.py get-attachment 67890 -o /tmp/fix.patch
```

Search by program name, then by DLL and symptom words. Read the candidates with `show`. Look for a patch (`attachments` marks patches with `[patch]`; obsolete ones are hidden unless you pass `--all`) and for a merge request link in the comments. If a ticket matches, tell the user the number and the summary. If nothing matches, say so. Attachment download is plain Bugzilla 5 REST and is not confirmed on WineHQ yet: if it fails, report the error and use the link in the ticket.

If there is no upstream bug yet, the fix can be catalogued in dllmgr under a dllmgr issue id: `dllmgr-<N>`, with the bug URL `https://github.com/unxed/dllmgr/issues/N`. Rename it when a WineHQ report is filed.

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

- Never edit the hunk headers of a unified diff by hand. Apply the existing patch to a pristine tree, edit the source, and regenerate the patch with `git diff`.
- Apply all patches selected for one module to the same pristine tree before building. A fix set builds each module once.
- A CI run reported as "cancelled" may mean only that one matrix job hit its timeout. Read the per-job conclusions and the artifacts before you discard the run.

For comctl32 in Wine 11 there are two modules: `comctl32` and `comctl32_v6`. Build the one the program loads (step 3). Build both if unsure.

When the user's Wine is a fork release (launcher runners often are), build from the fork's tag, not from a WineHQ tag:

```
FIW_WINE_GIT=https://github.com/OWNER/FORK.git tools/build_one_dll.sh FORK-TAG DLL
```

- Find the tree: the runner's PE modules often keep their build path in debug strings (`../TREE/dlls/DLL/file.c`), and the fork's release notes name the tag. Confirm the match before you patch: strip both DLLs (`x86_64-w64-mingw32-strip -o`) and compare their sets of printable strings; apart from paths they must be equal.
- A tree can need a newer toolchain than the distribution has. Example: a winebuild that puts delay-import data into `.didat$N` sections needs binutils 2.44 or newer. With 2.41 the DLL links, but the first delay-loaded call crashes with an access violation in `__delayLoadHelper2`. Check `objdump -h BUILT.dll | grep didat` against `x86_64-w64-mingw32-ld --version`. Use a matching toolchain, or a local build-only change back to `.idata$N` in `tools/winebuild/import.c`; then delete the build's `*.delay.a` files so the import libraries are regenerated. This change is not part of any fix; say so in the report.
- A crash inside your own build: the digest backtrace gives `DLL + offset`. Map it to a source line with `x86_64-w64-mingw32-addr2line -f -i -e BUILT.dll ADDR`, where ADDR is the PE ImageBase plus the offset.

### 5a. Waiting for a CI run

```
tools/ci_wait.py --repo OWNER/REPO --run ID --job NAME --artifact JOB:NAME --out DIR --stall-min M
```

- Run the wait in the background and keep working. Do not block on a polling loop.
- Wait for the specific job, not the whole run. The tool fetches its artifact as soon as the job is done; read it then.
- An empty or missing job list is never "done". Test that the job exists and is completed.
- Do not push to a branch whose run you are waiting for: `cancel-in-progress` cancels the run. Batch commits locally and push once the result is in.
- Set `--stall-min` to about 2-3x the job's normal duration. A stall (or a cancelled or failed run) is a failure to investigate, not a reason to keep waiting.

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

Measuring from outside:

- Under Wine, `GetScrollInfo` on a window of another process returns FALSE: the scroll state lives in the owner process's user32. An external observer then logs no scroll position, without any error.
- Measure scrolling by reading item 0's rectangle with `LVM_GETITEMRECT`, through memory allocated in the target process (`VirtualAllocEx`, `WriteProcessMemory`, `ReadProcessMemory`). For a 32-bit target keep the buffer below 4 GB.
- Before you conclude "it did not move", check that the measurement fields are present in the log.
- Compare screenshots by cropping the same region from the baseline, the candidate and the Windows captures at the same DPI. Describe concrete differences: which element crosses which frame.
- Judge on-screen pixels from the X server (`import -window root`, `XGetImage`), not from Wine's screen DC: after an Expose that Wine did not present, `GetPixel(GetDC(NULL))` returned the window surface colour while X showed something else.
- Flicker and first-paint problems need a window manager without compositing (for example Metacity `--compositor=none`). A compositor (mutter, Muffin, KWin) hides or reorders short phases, so a pass there proves nothing.
- Many old programs are DPI-unaware: at 192 DPI Wine scales their coordinates by 2. Code that captures and draws for such a window must work in physical pixels on both sides, or it shows enlarged copies.
- With WineHQ packages (old WoW64) a 32-bit program loads `lib/wine/i386-unix/*.so`; in new-WoW64 builds only `x86_64-unix` exists. Rebuild and test the layout the program actually uses.
- Reproduce the user's launch path exactly (menu entry, file manager, `wine`, a launcher): an app-private runtime or override applies only to the paths that use it.
- Accessibility-based desktop automation does not see Wine windows (they expose no AT-SPI tree). Capture a window with `xwd -id WID` (find WID with `wmctrl -l`). Under a compositor, the capture of a covered window contains the windows on top of it: raise it first (`wmctrl -i -a WID`) and give focus back after. Areas the program never paints show stale content (whatever was there before), not black.
- GPU output in a child window (DXVK, vkd3d-proton, OpenGL) goes to an offscreen X client window (listed under a 1x1 parent in `xwininfo -root -tree`) and Wine copies it into the toplevel on each present. `xwd -id` on such a redirected window returns screen content, not the window's pixels. Read them with `XCompositeNameWindowPixmap` and `XGetImage` on the returned pixmap (Python `ctypes`, no extra packages). Compare that pixmap (what was presented) with the toplevel (what is on screen) at the same moment, sampled about once a second while the user interacts: this separates "renders wrong" from "copied or overwritten wrong". Report how many samples match. Counting how often a region changes in each of the two gives the presented and the displayed frame rate.

### 8. Order of fix methods

Use the first that works:

1. A fix from the ticket: apply the ticket's patch to the source tree, build, enable, verify.
2. A small fix in Wine's C code, on the tag of the user's version. Write the smallest change that fixes the behaviour. Base it on Microsoft documentation and Wine tests, not on Microsoft binaries.
3. A change in a DLL that cannot be replaced (8a). Use dllmgr's application-private Wine runtime ([app isolation](https://github.com/unxed/dllmgr/blob/main/docs/app-isolation.md)): a CI-built runtime package can carry patched Unix modules for one program (first group: `win32u.so` + `winex11.so`). Or work around from the program's side: a proxy DLL that the program already imports, installed next to the program with a per-program load order, can hook window messages through public APIs (example: dllmgr `patches/dllmgr-27`, which pre-presents the screen under a newly shown window so no white or black is shown before the first paint).
4. A rewrite of the module in Bp. Rare. Only when the Wine module does not fit the program by design. Wine will not accept this code, so the upstream report stays text only.

Not fixed by this skill (report only): wineserver, graphics and drivers, timings, DRM and anti-cheat.

### 8a. DLLs that cannot be replaced

These cannot be replaced with the tools above: DLLs that have a unix part, and core DLLs: `ntdll`, `kernel32`, `kernelbase`, `user32`, `gdi32`, `win32u`, `winex11.drv`. A DLL has a unix part if the Wine installation has a matching `.so` next to its PE modules, for example `ls /usr/lib/*/wine/*-unix/DLL.so /usr/lib/wine/*-unix/DLL.so /opt/wine*/lib/wine/*-unix/DLL.so 2>/dev/null` prints a file. Do not run `override.py` for them. Identify the cause, write the report (step 10), and use method 3 of step 8 if dllmgr supports the program; otherwise tell the user that a local fix is not possible yet.

When a launcher keeps its runners in a directory of its own (Bottles, Lutris), such a fix can still stay limited to one bottle, with the user's yes:

- Make a hard-linked copy of the runner next to the original (`cp -al`, same filesystem, almost no disk space). In the copy, remove each file you replace before writing it, so the original runner keeps its own file. Keep the builtin mark on PE files: they load as the runner's builtins. The user selects the copy for that one bottle; undo is selecting the original runner again.
- `WINEDLLPATH` cannot do this: the runner's own library directory is searched first.
- A rebuilt unix module must have the same optional libraries as the runner's, or fonts or Vulkan break without an error. Configure with the same features, then compare both files: `nm -D --defined-only`, the `NEEDED` entries, the dlopen sonames (`strings FILE | grep '\.so\.'`) and the debug format strings.
- Verify with the digest (`dll X: builtin` from the copy's path, the missing import gone) and from the launcher itself (`/proc/PID/maps` of the running program shows which files are loaded).

### 9. Minimal reproducer (when you write your own fix or a report)

Write a small C program (mingw) that shows the bug without the application: create the control, send the message, print the result, return a non-zero exit code on the bug. Run it before and after the fix. It is the proof of the bug and the base of the test in the report.

Windows reference behaviour comes from running the same kind of probe on real Windows, for example a `windows-latest` GitHub Actions job: build with mingw on Linux, run on Windows, print one line per case. Make the probe cover argument errors, defaults, reset and last-error values, then make Wine's output identical line by line. This is black-box testing and fits rule 6.

A gate is valid only if it fails on the known-bad variant: before trusting a new test, run it once on the unfixed or deliberately broken build.

`wine: Unimplemented function DLL.Name called` means Wine does not export a function the program imports; the loader bound an aborting stub. Check the current Wine master (`git fetch --depth 1 origin master`), then implement the export with Windows-measured semantics.

`wine: Call from ADDR to unimplemented function DLL.dll.N` is the same for an import by ordinal N. The digest's `missing imports` names the importing module. When a spec gives no explicit ordinals, Wine numbers the exports in spec order, which matches Windows only where the spec was written that way (d2d1 is). Name the function from a Wine release that already exports ordinal N (compare the module's exports across Wine versions), check that the other ordinals the program imports from that module map to plausible functions, then find the upstream commit with `git log -- dlls/DLL/DLL.spec`. When the stub is hit inside a window procedure, Wine logs `user_callback_handler ignoring exception 80000100` and unwinds the callback; locks the program held there stay taken, so the visible symptom can be a hang or an unpainted window rather than a crash.

A new export can open a code path that uses further stubs. Rerun after each step: the next fixme on the same thread names the next missing piece. Example: a backported d2d1 export led to geometry-realization stubs, and the UI drew only after those were filled too. Each piece is its own patch; record its author and commit.

Wine constants are often calibrated on default sizes. Example: `LISTVIEW_SCROLL_ICON_LINE_SIZE = 37` is half of the default 74-pixel icon spacing. Native v6 scrolls lines × (item spacing on that axis) / 2 per wheel detent, so with 138×144 cells Wine was about 12× slower at 192 DPI. A fixture with default 32×32 icons passes either way. Calibrate against Windows with the application's real sizes and DPI, and put a non-default size in the fixture.

### 10. Report

Write the report using `templates/bug-report.md`. Fill every section.

Self-check: give a cheaper subagent only the report text and the Wine source tree (no other context, no access to your notes). It must write a patch from the text, the patch must build, and the reproducer must pass. If it fails, the report lacks precision: find what was missing, fix the text, check again.

Retest on the latest Wine before you propose any report or comment. Wine developers want reports against current wine.git; a report against a release that is months old is "not very useful" to them, and the bug may already be fixed. Build the current wine.git master (or the latest development release, if the build is not possible), run the reproducer and the real application there, and write down the commit you tested. If a developer in the ticket names a commit that should fix it, test exactly that commit (and master). Then: still broken → the report says "still present in wine-<version>-<commit>" with the results from that build; fixed → no new report; for a ticket that is already filed, propose a short comment confirming the fix (or what is left) and the commit tested. A report that was filed before this retest gets the same retest afterwards, with an updating comment if the results differ.

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

In Claude Code cloud sessions GitHub GraphQL is blocked: use `gh api` REST. Issues of repositories that are not attached to the session cannot be read with `gh`: read the public web page instead.
