# Vision

The owner's view of why fix-it-in-wine and dllmgr exist. Recorded on
2026-11-06. The full page, with the owner's points on reviving the Wine
ecosystem, the editorial notes **[Note N]** and the plan table, is
[dllmgr's vision.md](https://github.com/unxed/dllmgr/blob/main/docs/vision.md). This copy keeps the owner's text and a short
summary of the notes, so the skill's readers see them here too.

## The owner's text

### Original (Russian, verbatim)

> Поскольку Wine не берут код из LLM, скилл контрибьютит в Багзиллу словесное
> описание не только бага, но и того, как работает его фикс, и того, как эта
> логика тестировалась и с каким результатом. И ведёт свою базу фиксов
> параллельную, чтоб от апстрима не зависеть.
>
> И там тулза специально под это сделанная используется, dllmgr, это как
> playonlinux и прочие bottles, только с гранулярностью не до версии wine, а до
> DLL и конкретных заплаток. winetricks на стероидах, где вместо нативных либ -
> вайновские с ИИ фиксами (хочешь - бери бинарник, хочешь - словесное описание,
> и пусть агент у тебя прямо в коде вайна поправит и соберёт).

### English rendering

> Since Wine does not take code from LLMs **[Note 1]**, the skill contributes to
> Bugzilla **[Note 2]** a description in words not only of the bug, but also of
> how its fix works, and of how that logic was tested and with what result
> **[Note 3]**. And it keeps its own parallel database of fixes, so as not to
> depend on upstream.
>
> And it uses a tool made specially for this, dllmgr. It is like PlayOnLinux
> and the likes of Bottles, only the granularity is not a Wine version but a
> DLL and specific patches. winetricks on steroids, where instead of native
> libraries you get Wine's own, with AI fixes (take the binary if you want, or
> take the description in words and let your agent fix it right in the Wine
> code and build it **[Note 4]**).

In short, the notes say: Wine's
[Clean Room Guidelines](https://gitlab.winehq.org/wine/wine/-/wikis/Clean-Room-Guidelines)
do forbid LLM-generated code (Note 1); as of 2026-11-06 the skill has posted
nothing to Bugzilla yet, and posting needs the user's yes and the gate in step
10 of [SKILL.md](../SKILL.md) (Note 2); the description says what Windows does
and what to change, not the patch line by line (Note 3); the agent's code is
for the user's machine and the catalog, never for Wine (Note 4). Windows is
studied only as a black box (rule 6 of SKILL.md).
