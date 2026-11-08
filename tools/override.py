#!/usr/bin/env python3
"""Enable one DLL for one program in one Wine prefix, reversibly.

  override.py apply --prefix P --exe NAME.exe --dll FILE [--name comctl32.dll] [--slot system|sxs:<glob>|appdir]
  override.py undo  --prefix P --exe NAME.exe --name comctl32[.dll] [--force]
  override.py status --prefix P

A stand-in until dllmgr (https://github.com/unxed/dllmgr) exists.

Wine facts: a DLL built by another Wine build carries the "builtin" mark, so it
must be cleared (pe_unmark.unmark) or Wine loads its own builtin instead.
Per-program load order lives in
HKCU\\Software\\Wine\\AppDefaults\\<exe>\\DllOverrides (value "<name>" =
"native,builtin"). Without an override Wine prefers its builtin even when a
native file is present, so other programs are not affected.

Environment: FIW_WINE (wine command, default "wine").
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys

from pe_unmark import mark_of, unmark, pe_machine, NotPE, Placeholder  # noqa: F401

STATE_DIR = "fix-it-in-wine"
OVERRIDE_VALUE = "native,builtin"


class OverrideError(Exception):
    pass


# ---------- small pure helpers ----------

def sha256(data):
    return hashlib.sha256(data).hexdigest()


def norm(name):
    """Name without .dll, lower case: how entries and registry values match."""
    name = name.lower()
    return name[:-4] if name.endswith(".dll") else name


def reg_key(exe):
    return "HKCU\\Software\\Wine\\AppDefaults\\%s\\DllOverrides" % exe


def parse_reg_query(text, value):
    """Data of a REG_SZ value in `reg query` output, or None."""
    pat = re.compile(r"^\s*%s\s+REG_SZ\s+(.*?)\s*$" % re.escape(value), re.I)
    for line in text.splitlines():
        m = pat.match(line)
        if m:
            return m.group(1)
    return None


def prefix_arch(prefix):
    """'win32' or 'win64' from the '#arch=' line of system.reg."""
    path = os.path.join(prefix, "system.reg")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"#arch=(win32|win64)\s*$", line)
                if m:
                    return m.group(1)
    except OSError:
        raise OverrideError("%s is not a Wine prefix (cannot read system.reg)" % prefix)
    raise OverrideError("no '#arch=' line in %s" % path)


def slot_dir(prefix, slot, dll_arch, pfx_arch, exe_path=None):
    """Directory the DLL goes to."""
    win = os.path.join(prefix, "drive_c", "windows")
    if slot == "system":
        if dll_arch == "i386":
            return os.path.join(win, "syswow64" if pfx_arch == "win64" else "system32")
        if dll_arch == "x86_64":
            if pfx_arch == "win32":
                raise OverrideError("x86_64 DLL cannot go into a win32 prefix")
            return os.path.join(win, "system32")
        raise OverrideError("unsupported DLL architecture %s" % dll_arch)
    if slot.startswith("sxs:"):
        pattern = slot[4:]
        base = os.path.join(win, "winsxs")
        matches = sorted(p for p in glob.glob(os.path.join(base, pattern)) if os.path.isdir(p))
        if len(matches) != 1:
            listing = "".join("\n  " + m for m in matches) or " none"
            raise OverrideError("slot %s must match exactly one directory in %s, found:%s"
                                % (slot, base, listing))
        return matches[0]
    if slot == "appdir":
        if not exe_path:
            raise OverrideError("appdir slot requires --exe")
        drive_c = os.path.join(prefix, "drive_c")
        exe_full = exe_path if os.path.isabs(exe_path) else None
        if exe_full is None:
            # --exe may be a bare name (e.g. FSViewer.exe); search drive_c for it.
            matches = []
            for root, _dirs, files in os.walk(drive_c):
                for fn in files:
                    if fn.lower() == exe_path.lower():
                        matches.append(os.path.join(root, fn))
            if len(matches) != 1:
                listing = "".join("\n  " + m for m in matches) or " none"
                raise OverrideError("appdir slot: expected one %s under drive_c, found:%s"
                                    % (exe_path, listing))
            exe_full = matches[0]
        exe_full = os.path.normpath(exe_full)
        if not os.path.exists(exe_full):
            raise OverrideError("exe not found: %s" % exe_full)
        return os.path.dirname(exe_full)
    raise OverrideError("unknown slot %r (use system, sxs:<glob>, or appdir)" % slot)


# ---------- files and state ----------

def state_path(prefix):
    return os.path.join(prefix, STATE_DIR, "state.json")


def load_state(prefix):
    try:
        with open(state_path(prefix), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"entries": []}
    except (OSError, ValueError) as e:
        raise OverrideError("cannot read %s: %s" % (state_path(prefix), e))


def write_atomic(path, data, mode=None):
    """Write via a temp file in the same dir + os.replace (replaces a symlink itself)."""
    tmp = os.path.join(os.path.dirname(path), ".fiw-tmp-%d" % os.getpid())
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except OSError as e:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise OverrideError("cannot write %s: %s" % (path, e.strerror or e))


def save_state(prefix, state):
    os.makedirs(os.path.dirname(state_path(prefix)), exist_ok=True)
    write_atomic(state_path(prefix), json.dumps(state, indent=2).encode("utf-8"))


def read_file(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as e:
        raise OverrideError("cannot read %s: %s" % (path, e.strerror or e))


def file_sha(path):
    try:
        with open(path, "rb") as f:
            return sha256(f.read())
    except OSError:
        return None


def find_entry(state, exe, name):
    for e in state["entries"]:
        if e["exe"].lower() == exe.lower() and norm(e["name"]) == norm(name):
            return e
    return None


# ---------- wine registry ----------

def run_wine(prefix, *args):
    env = dict(os.environ, WINEPREFIX=prefix)
    wine = os.environ.get("FIW_WINE", "wine")
    try:
        return subprocess.run([wine] + list(args), env=env, capture_output=True, text=True)
    except OSError as e:
        raise OverrideError("cannot run %r: %s (set FIW_WINE?)" % (wine, e.strerror or e))


def reg_query(prefix, exe, value):
    r = run_wine(prefix, "reg", "query", reg_key(exe), "/v", value)
    return parse_reg_query(r.stdout, value) if r.returncode == 0 else None


def reg_add(prefix, exe, value, data):
    r = run_wine(prefix, "reg", "add", reg_key(exe), "/v", value, "/d", data, "/f")
    if r.returncode != 0:
        raise OverrideError("wine reg add failed: %s" % (r.stderr.strip() or r.returncode))


def reg_delete(prefix, exe, value):
    r = run_wine(prefix, "reg", "delete", reg_key(exe), "/v", value, "/f")
    if r.returncode != 0:
        raise OverrideError("wine reg delete failed: %s" % (r.stderr.strip() or r.returncode))


def conflicting_overrides(prefix, exe, dll):
    """Find registry overrides of `dll` that could load a shared DLL file
    in a program other than `exe`.

    Returns a list of (key_path, value) tuples, or [] when no conflicts.
    Checked: global HKCU\\Software\\Wine\\DllOverrides\\<dll>,
             wildcard *<dll>, and per-exe AppDefaults\\<other_exe>\\DllOverrides\\<dll>.
    """
    dll = norm(dll)
    conflicts = []

    # 1. Global override: HKCU\Software\Wine\DllOverrides\<dll>
    r = run_wine(prefix, "reg", "query", "HKCU\\Software\\Wine\\DllOverrides", "/v", dll)
    if r.returncode == 0:
        v = parse_reg_query(r.stdout, dll)
        if v is not None:
            conflicts.append(("HKCU\\Software\\Wine\\DllOverrides", v))

    # 2. Wildcard override: HKCU\Software\Wine\DllOverrides\*<dll>
    r = run_wine(prefix, "reg", "query", "HKCU\\Software\\Wine\\DllOverrides", "/v", "*" + dll)
    if r.returncode == 0:
        v = parse_reg_query(r.stdout, "*" + dll)
        if v is not None:
            conflicts.append(("HKCU\\Software\\Wine\\DllOverrides (wildcard)", v))

    # 3. Per-exe overrides for every other executable in AppDefaults.
    r = run_wine(prefix, "reg", "query", "HKCU\\Software\\Wine\\AppDefaults")
    if r.returncode == 0:
        for line in r.stdout.splitlines():
            line = line.strip()
            if not line or not line.startswith("HKEY_CURRENT_USER\\"):
                continue
            m = re.match(
                r"HKEY_CURRENT_USER\\Software\\Wine\\AppDefaults\\([^\\]+)\\DllOverrides$", line)
            if not m:
                continue
            other_exe = m.group(1)
            if other_exe.lower() == exe.lower():
                continue
            sub = run_wine(prefix, "reg", "query", line, "/v", dll)
            if sub.returncode == 0:
                v = parse_reg_query(sub.stdout, dll)
                if v is not None:
                    conflicts.append(("HKCU\\Software\\Wine\\AppDefaults\\%s\\DllOverrides"
                                      % other_exe, v))

    return conflicts


# ---------- commands ----------

def cmd_apply(args):
    prefix = os.path.abspath(args.prefix)
    arch = prefix_arch(prefix)
    name = args.name or os.path.basename(args.dll)
    value = norm(name)
    state = load_state(prefix)
    if find_entry(state, args.exe, name):
        raise OverrideError("%s for %s is already applied, undo first" % (name, args.exe))

    raw = read_file(args.dll)
    try:
        dll_arch = pe_machine(raw)
        new = unmark(raw)
    except NotPE as e:
        raise OverrideError("%s is not a usable PE file: %s" % (args.dll, e))
    except Placeholder:
        raise OverrideError("%s is a Wine placeholder file without code" % args.dll)
    is_appdir = args.slot == "appdir"
    dest = os.path.join(slot_dir(prefix, args.slot, dll_arch, arch, args.exe), name)
    if not is_appdir and not os.path.lexists(dest):
        raise OverrideError("nothing to replace at %s" % dest)
    new_sha = sha256(new)

    same = [e for e in state["entries"] if e["dest"] == dest]
    for e in same:
        if e["new_sha256"] != new_sha:
            raise OverrideError("%s is already replaced by a different DLL for %s %s"
                                % (dest, e["exe"], e["name"]))

    # For shared slots (system / sxs:) the file is visible to every program
    # in the prefix. Guard against any other registry override of the same
    # DLL that could load our shared file in a different program.
    if not is_appdir:
        conflicts = conflicting_overrides(prefix, args.exe, name)
        if conflicts:
            detail = "; ".join("%s=%s" % (k, v) for k, v in conflicts)
            raise OverrideError(
                "refusing to install shared %s for %s: another override of %s "
                "could load this file in a different program: %s"
                % (name, args.exe, name, detail))

    print_lines = []
    wrote = None                      # original bytes + mode if we replaced the file
    backup = None                     # backup path (None when no original existed)
    orig_sha = None                   # sha of original (None when no original existed)
    if same:
        orig_sha, backup = same[0]["orig_sha256"], same[0]["backup"]
        print_lines.append("shared %s (already replaced for %s)" % (dest, same[0]["exe"]))
    elif os.path.lexists(dest):
        orig = read_file(dest)
        orig_sha = sha256(orig)
        backup = os.path.join(prefix, STATE_DIR, "backup", orig_sha)
        if not os.path.exists(backup):
            os.makedirs(os.path.dirname(backup), exist_ok=True)
            write_atomic(backup, orig)
        mode = os.stat(dest).st_mode & 0o7777
        write_atomic(dest, new, mode)
        wrote = (orig, mode)
        print_lines.append("backup: %s" % backup)
        print_lines.append("replaced %s" % dest)
    else:
        # App-dir slot: creating a new file next to the exe, nothing to back up.
        mode = 0o644
        write_atomic(dest, new, mode)
        wrote = (None, mode)
        print_lines.append("installed %s" % dest)

    try:
        before = reg_query(prefix, args.exe, value)
        reg_add(prefix, args.exe, value, OVERRIDE_VALUE)
    except OverrideError:
        if wrote and wrote[0] is not None:
            write_atomic(dest, wrote[0], wrote[1])
        elif wrote and not os.path.lexists(dest):
            # We created a new file; roll back by removing it.
            try:
                os.unlink(dest)
            except OSError:
                pass
        raise
    state["entries"].append({
        "exe": args.exe, "name": name, "dest": dest, "backup": backup,
        "orig_sha256": orig_sha, "new_sha256": new_sha, "reg_before": before})
    save_state(prefix, state)
    for line in print_lines:
        print(line)
    print("registry: %s  %s=%s" % (reg_key(args.exe), value, OVERRIDE_VALUE))
    print("to undo: %s undo --prefix %s --exe %s --name %s" % (
        shlex.quote(os.path.abspath(__file__)), shlex.quote(prefix),
        shlex.quote(args.exe), shlex.quote(name)))
    return 0


def cmd_undo(args):
    prefix = os.path.abspath(args.prefix)
    state = load_state(prefix)
    entry = find_entry(state, args.exe, args.name)
    if not entry:
        raise OverrideError("no applied entry for %s %s" % (args.exe, args.name))
    dest = entry["dest"]
    dest_exists = os.path.lexists(dest)
    if dest_exists and file_sha(dest) != entry["new_sha256"] and not args.force:
        raise OverrideError("file changed outside fix-it-in-wine: %s (use --force)" % dest)
    others = [e for e in state["entries"] if e is not entry and e["dest"] == dest]
    backup = entry["backup"]

    value = norm(entry["name"])
    if entry["reg_before"] is None:
        reg_delete(prefix, entry["exe"], value)
        print("registry: removed %s of %s" % (value, entry["exe"]))
    else:
        reg_add(prefix, entry["exe"], value, entry["reg_before"])
        print("registry: %s of %s set back to %s" % (value, entry["exe"], entry["reg_before"]))

    if not dest_exists:
        print("file already absent: %s" % dest)
    elif others:
        print("kept %s (still used by %s)" % (dest, others[0]["exe"]))
    elif backup is None:
        # App-dir slot with no original: the file was created by us, remove it.
        os.unlink(dest)
        print("removed %s" % dest)
    else:
        orig = read_file(backup)
        mode = os.stat(dest).st_mode & 0o7777 if os.path.exists(dest) else None
        write_atomic(dest, orig, mode)
        print("restored %s" % dest)
    state["entries"].remove(entry)
    save_state(prefix, state)
    return 0


def cmd_status(args):
    prefix = os.path.abspath(args.prefix)
    entries = load_state(prefix)["entries"]
    for e in entries:
        ok = file_sha(e["dest"]) == e["new_sha256"]
        print("%s %s -> %s (%s)" % (e["exe"], e["name"], e["dest"], "ok" if ok else "changed"))
    if not entries:
        print("no entries")
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="override.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("apply", help="replace a Wine DLL and enable it for one program")
    a.add_argument("--prefix", required=True)
    a.add_argument("--exe", required=True)
    a.add_argument("--dll", required=True)
    a.add_argument("--name")
    a.add_argument("--slot", default="system")
    u = sub.add_parser("undo", help="revert an apply")
    u.add_argument("--prefix", required=True)
    u.add_argument("--exe", required=True)
    u.add_argument("--name", required=True)
    u.add_argument("--force", action="store_true")
    s = sub.add_parser("status", help="list applied overrides")
    s.add_argument("--prefix", required=True)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    handlers = {"apply": cmd_apply, "undo": cmd_undo, "status": cmd_status}
    try:
        return handlers[args.cmd](args)
    except OverrideError as e:
        print("override: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
