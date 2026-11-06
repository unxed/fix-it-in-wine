#!/usr/bin/env python3
"""Run a Windows program under Wine with debug channels and digest the log.

  wineprobe.py run [--prefix P] [--preset NAME | --debug STR] [--dll NAME]...
                   [--out DIR] [--timeout SEC] -- EXE [ARGS...]
  wineprobe.py digest LOG [--dll NAME]... [--max-lines N]

Environment: FIW_WINE (wine command), FIW_WORK (work dir).
"""
import argparse
import collections
import datetime
import os
import re
import subprocess
import sys

# Wine may prefix the debug class with pid and tid ("0024:0028:trace:...").
DEBUG_RE = re.compile(
    r"^(?:[0-9a-f]{4}:){0,2}(trace|warn|err|fixme):([\w.-]+):(\S+) ?(.*)$")
# trace:loaddll prints: Loaded L"C:\\windows\\...\\x.dll" at 7B000000: native
# (debugstr_w doubles the backslashes).
LOAD_RE = re.compile(r'Loaded L"(.*?)" at [0-9a-fA-F]+: (native|builtin)')
MISSING_RE = re.compile(
    r'No implementation for (\S+?)(?: imported from (L?"[^"]*"|[^\s,]+))?, setting')

PRESETS = {
    "load": "+loaddll,warn+module",
    "crash": "+loaddll,+seh,warn+module",
}


class ProbeError(Exception):
    pass


def work_dir():
    return os.environ.get("FIW_WORK") or os.path.expanduser("~/.cache/fix-it-in-wine")


def debug_string(preset=None, debug=None):
    """WINEDEBUG value for a preset name or an explicit string."""
    if debug:
        return debug
    preset = preset or "load"
    if preset in PRESETS:
        return PRESETS[preset]
    if preset.startswith("channels:"):
        names = [c for c in preset[len("channels:"):].split(",") if c]
        if not names:
            raise ProbeError("preset 'channels:' needs channel names, e.g. channels:relay,seh")
        return PRESETS["load"] + "".join("," + "+" + n.lstrip("+") for n in names)
    raise ProbeError("unknown preset %r (use load, crash or channels:a,b)" % preset)


def unescape_path(path):
    return path.replace("\\\\", "\\")


def basename(path):
    return re.split(r"[\\/]", path)[-1]


def module_name(name):
    """Basename without .dll, lower case: how modules are compared."""
    name = basename(name).lower()
    return name[:-4] if name.endswith(".dll") else name


def truncate(text, width):
    return text if len(text) <= width else text[:width]


def import_source(raw):
    """Basename of the 'imported from' operand (L"path" or plain name)."""
    raw = raw.strip()
    if raw.startswith("L"):
        raw = raw[1:]
    return basename(unescape_path(raw.strip('"')))


def parse_log(lines):
    loads = []                       # (windows path, native|builtin)
    missing = collections.OrderedDict()
    exceptions = []
    errors = collections.OrderedDict()
    fixme = collections.Counter()
    for line in lines:
        line = line.rstrip("\r\n")
        if "Unhandled" in line:
            exceptions.append(line.strip())
        m = DEBUG_RE.match(line)
        if not m:
            continue
        cls, chan, func, msg = m.groups()
        key = chan + ":" + func
        lm = LOAD_RE.search(line)
        if lm:
            loads.append((unescape_path(lm.group(1)), lm.group(2)))
        mm = MISSING_RE.search(line)
        if mm:
            item = mm.group(1)
            if mm.group(2):
                item += " (from %s)" % import_source(mm.group(2))
            missing.setdefault(item, None)
        if cls == "err" and key not in errors:
            errors[key] = key + " " + msg
        if cls == "fixme":
            fixme[key] += 1
    return loads, missing, exceptions, errors, fixme


def make_digest(lines, dlls=(), max_lines=60, notes=()):
    """Digest of a debug log as a list of lines, at most max_lines long."""
    loads, missing, exceptions, errors, fixme = parse_log(lines)
    out = list(notes)
    for name in dlls:
        want = module_name(name)
        hits = [(p, mode) for p, mode in loads if module_name(p) == want]
        if not hits:
            out.append("dll %s: not loaded" % name)
        for path, mode in hits:
            out.append("dll %s: %s %s" % (name, mode, path))
    modules = {}
    for path, mode in loads:
        modules[path.lower()] = (path, mode)
    native = [basename(p) for p, mode in modules.values() if mode == "native"]
    out.append("modules: %d loaded (%d native)" % (len(modules), len(native)))
    if native:
        out.append("native: " + ", ".join(native[:15]))
    if missing:
        out.append("missing imports:")
        out += ["  " + m for m in list(missing)[:10]]
    if exceptions:
        out.append("exceptions:")
        out += ["  " + truncate(e, 160) for e in exceptions[:5]]
    if errors:
        out.append("errors:")
        out += ["  " + truncate(e, 160) for e in list(errors.values())[:10]]
    if fixme:
        out.append("fixme top:")
        out += ["  %s x%d" % kv for kv in fixme.most_common(5)]
    max_lines = max(1, max_lines)
    if len(out) > max_lines:
        extra = len(out) - (max_lines - 1)
        out = out[:max_lines - 1] + ["... %d more lines omitted" % extra]
    return out


def read_lines(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError as e:
        raise ProbeError("cannot read log %s: %s" % (path, e.strerror or e))


def cmd_digest(args):
    lines = read_lines(args.log)
    print("\n".join(make_digest(lines, args.dll, args.max_lines)))
    return 0


def cmd_run(args, command):
    if not command:
        raise ProbeError("no program given: use  run [options] -- EXE [ARGS...]")
    wine = os.environ.get("FIW_WINE", "wine")
    env = dict(os.environ)
    env["WINEDEBUG"] = debug_string(args.preset, args.debug)
    if args.prefix:
        env["WINEPREFIX"] = args.prefix
    out_dir = args.out or os.path.join(work_dir(), "logs")
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = os.path.join(out_dir, "%s-%s.log" % (stamp, basename(command[0])))
    notes = []
    with open(log_path, "wb") as log:
        try:
            proc = subprocess.Popen([wine] + command, env=env,
                                    stdout=subprocess.DEVNULL, stderr=log)
        except OSError as e:
            raise ProbeError("cannot run %r: %s (set FIW_WINE?)" % (wine, e.strerror or e))
        try:
            proc.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            notes.append("timed out after %s s, wine was killed" % args.timeout)
    print("\n".join(make_digest(read_lines(log_path), args.dll, args.max_lines, notes)))
    print("full log: " + log_path)
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="wineprobe.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run EXE under Wine and print a digest of the log")
    r.add_argument("--prefix")
    g = r.add_mutually_exclusive_group()
    g.add_argument("--preset", help="load (default), crash or channels:a,b")
    g.add_argument("--debug", help="explicit WINEDEBUG string")
    r.add_argument("--dll", action="append", default=[])
    r.add_argument("--out")
    r.add_argument("--timeout", type=float, default=60.0)
    r.add_argument("--max-lines", type=int, default=60)
    d = sub.add_parser("digest", help="digest of an existing log")
    d.add_argument("log")
    d.add_argument("--dll", action="append", default=[])
    d.add_argument("--max-lines", type=int, default=60)
    return ap


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    command = []
    if "--" in argv:                 # everything after -- is the program command line
        i = argv.index("--")
        argv, command = argv[:i], argv[i + 1:]
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "run":
            return cmd_run(args, command)
        return cmd_digest(args)
    except ProbeError as e:
        print("wineprobe: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
