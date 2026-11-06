# Upstream bug report template

Fill every section. Write facts, not guesses. If a fact is unknown, write "unknown" and say why. Remove these instructions before posting.

The text is posted only after the user has approved it, and only after the gate in step 10 of `SKILL.md` has passed.

Wine does not accept LLM-generated code ([Clean Room Guidelines](https://gitlab.winehq.org/wine/wine/-/wikis/Clean-Room-Guidelines)). Do not paste or attach code the agent wrote: describe it in words. Code written by a person (for example a patch already in the ticket) may be referenced as usual.

## Title

`<component>: <wrong behaviour in one line> (breaks <Program>)`

Example: `comctl32: toolbar items are not drawn after window resize (breaks ExampleViewer)`

## Program

- Name:
- Version:
- Where to get it (download link):

## Wine versions

- Bad (shows the bug):
- Good (works), if any:

## Regression

One of:

- Regression commit: `<hash>` `<subject>`, found by `<release bisect / git bisect>`.
- Not a regression: the bug is present in every version checked (list them).
- Unknown.

## Symptom

What the user sees. What is expected instead. Add a screenshot or the exact error text when it helps.

## How to reproduce

Numbered steps in the program, starting from a clean prefix if the bug needs it. Say which Windows version is set in winecfg.

1.
2.
3.

## Minimal reproducer

A short C program (mingw) that shows the bug without the application, or the reason why none could be made. If the agent wrote it, do not paste the source: describe it in the "Test" section below and give a link to it (for example the dllmgr catalog entry), saying that it was written with AI help. Give the expected and actual output.

Result on the bad version:

Result on the good version:

## Cause

- File:
- Function:
- Line, at commit `<hash>`:
- What the code does now:
- What it should do, and why. Links to Microsoft documentation:

Do not use disassembled Microsoft code or leaked sources. State the sources: Microsoft documentation, Wine tests, observed behaviour.

## Fix

Steps, each with the file and function. Name the edge cases and say how each is handled.

1.
2.
3.

Edge cases:

- 

If a person wrote a patch, attach it as a file to the bug, not as text in the comment. If the agent wrote it, do not attach it: the steps above are the fix. You may link the dllmgr catalog entry that holds it, saying that it was written with AI help and is not offered for inclusion in Wine.

## Test for dlls/<dll>/tests

In words, so that a developer can write the test without this report's author:

- Setup (windows, controls, styles, data to create):
- Actions (messages sent, calls made, in order):
- Expected values (result of each call, with the value that must be returned and the value returned now):

## How it was checked

- Wine version and commit the fix was built on:
- The DLL that was built and how it was enabled:
- Minimal reproducer before and after:
- The application before and after (confirmed by the user by eye):
- Report self-check: a subagent got only this text and the Wine tree, wrote a patch, the patch built, and the reproducer passed. State yes or no. If no, say what was missing. This patch is for the check only and is not posted.

## Disclosure

This report was prepared with an AI agent (fix-it-in-wine). The code the agent wrote is not offered for inclusion in Wine.
