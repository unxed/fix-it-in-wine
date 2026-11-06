# fix-it-in-wine

A skill for AI agents. A Windows program misbehaves under Wine on your Linux machine. You describe the problem to your agent and give it this skill. The agent:

1. finds which Wine DLL is at fault;
2. finds the matching ticket in WineHQ Bugzilla;
3. builds that one DLL from Wine sources, without building all of Wine;
4. fixes it, or applies the fix from the ticket;
5. enables the DLL for that program only, in that prefix only, with a one-step rollback;
6. offers an upstream report: a new bug or a comment in an existing ticket.

You do three things: log in to WineHQ Bugzilla, confirm the result by eye, and approve sending. Nothing is posted without your yes. The system Wine is never modified.

The design is in [docs/concept.md](docs/concept.md). The instructions for the agent are in [SKILL.md](SKILL.md).

## Status

Proof of concept. The tools below exist. Some bugs cannot be fixed locally yet: DLLs with a unix part and core DLLs (ntdll, kernel32, kernelbase, user32, gdi32, win32u, winex11.drv). For them the skill writes a report only.

## Install

Claude Code: clone the repository into the skills directory, so that `SKILL.md` is at the root of the skill:

```
git clone https://github.com/unxed/fix-it-in-wine ~/.claude/skills/fix-it-in-wine
```

Other agents: point the agent to `SKILL.md` in this repository (or in your clone) and let it read the file.

## Requirements

- Linux with Wine installed, and the program you want to fix.
- Python 3 (standard library only) for all Python tools.
- For `tools/build_one_dll.sh`: git, gcc, make, flex, bison, and the mingw-w64 compilers. On Debian, Ubuntu and Mint:

  ```
  sudo apt install git gcc make flex bison gcc-mingw-w64-i686 gcc-mingw-w64-x86-64
  ```

- Disk space for one Wine source tree and one build tree. In a check with `wine-11.0` they were 389 MB and 164 MB.
- A WineHQ Bugzilla account, if you want to send a report.

## Layout

```
SKILL.md                  instructions for the agent
docs/concept.md           design of the skill
templates/bug-report.md   upstream report template
tools/pe_unmark.py        clears the "Wine builtin DLL" mark of a PE file
tools/build_one_dll.sh    builds one DLL from a Wine tag, branch or commit
tools/wineprobe.py        runs a program with debug channels, prints a short digest of the log
tools/winebugs.py         read-only WineHQ Bugzilla client: search, show, attachments
tools/override.py         enables one DLL for one program in one prefix; apply, undo, status
tests/                    unit tests of the tools
```

Settings through environment variables: `FIW_WINE` (the wine command, default `wine`), `FIW_WORK` (work directory, default `~/.cache/fix-it-in-wine`), `FIW_BUGZILLA` (Bugzilla REST base, default `https://bugs.winehq.org/rest`).

## Tests

```
python3 -m unittest discover -s tests
```

The tests need no network and no real Wine. CI runs them.

## Related projects

- [dllmgr](https://github.com/unxed/dllmgr): a manager of replacement DLLs for Wine. It will replace `tools/override.py` and `tools/wineprobe.py`.
- [Marwin](https://github.com/unxed/Marwin).

## License

BSD-3-Clause. See [LICENSE](LICENSE).

## Showcases

See [showcases/README.md](showcases/README.md): WineHQ bug 59609 (in progress), Far Manager 3 under Wine without modifying Far3 (planned), the Photoshop trial (planned, the final one).

## Related work

- Martin Alderson, [Using agents and Wine to move off Windows](https://martinalderson.com/posts/using-agents-and-wine-to-move-off-windows/) (2026-03-17): an agent got a Windows program working under Wine (a stub DLL built with mingw, binary patches, many test rounds).
- [LiberNT#108](https://github.com/LiberNT/LiberNT/issues/108): a proposal for a shared Wine fork that is easy for LLM agents to work on.
- [wine-environment-initialization-validation](https://www.skillsdirectory.com/skills/holobiomicslab-wine-environment-initialization-validation) (HolobiomicsLab, CC-BY-4.0): a checklist skill that validates a Wine + .NET environment for one tool. The preflight step and the "When NOT to use" and "Evaluation signals" sections of our SKILL.md follow its structure.
- Ideas for making the whole chain faster and more autonomous: [docs/ideas.md](docs/ideas.md).
