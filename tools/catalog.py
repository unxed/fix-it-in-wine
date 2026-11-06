#!/usr/bin/env python3
"""Read-only client for the dllmgr catalog of fixes and variants.

  catalog.py search [--program NAME] [--dll NAME] [--bug ID] [TEXT...]
  catalog.py show ID

Environment: FIW_CATALOG (URL or local path of index.json, default
https://raw.githubusercontent.com/unxed/dllmgr/main/catalog/index.json).
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_CATALOG = "https://raw.githubusercontent.com/unxed/dllmgr/main/catalog/index.json"
TIMEOUT = 30


class CatalogError(Exception):
    pass


def catalog_source():
    return os.environ.get("FIW_CATALOG") or DEFAULT_CATALOG


def load_index(source):
    """Entries of the index at a URL or a local path, as a list of dicts."""
    if source.startswith(("http://", "https://")):
        req = urllib.request.Request(source, headers={"User-Agent": "fix-it-in-wine"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            raise CatalogError("HTTP %d from %s" % (e.code, source))
        except (urllib.error.URLError, OSError) as e:
            raise CatalogError("cannot reach %s: %s" % (source, getattr(e, "reason", e)))
    else:
        try:
            with open(source, "rb") as f:
                raw = f.read()
        except OSError as e:
            raise CatalogError("cannot read %s: %s" % (source, e.strerror or e))
    try:
        entries = json.loads(raw.decode("utf-8"))
    except ValueError:
        raise CatalogError("%s is not a JSON index" % source)
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        raise CatalogError("%s: the index must be a JSON array of objects" % source)
    return entries


def _norm_name(name):
    """Lower case, without surrounding blanks and without a .exe or .dll suffix."""
    name = str(name or "").strip().lower()
    for suffix in (".exe", ".dll"):
        if name.endswith(suffix):
            return name[:-len(suffix)]
    return name


def _entry_dlls(entry):
    dlls = list(entry.get("dlls") or [])
    if "dll" in entry:
        dlls.append(entry["dll"])
    return [_norm_name(d) for d in dlls]


def _entry_programs(entry):
    return [_norm_name(p) for p in entry.get("programs") or []]


def _bug_key(bug):
    """A WineHQ number becomes its entry id; anything else is compared as an id."""
    key = str(bug).strip().lower()
    return "winehq-" + key if key.isdigit() else key


def match(entry, program=None, dll=None, bug=None, words=()):
    """True if the entry passes every given filter."""
    if program and _norm_name(program) not in _entry_programs(entry):
        return False
    if dll and _norm_name(dll) not in _entry_dlls(entry):
        return False
    if bug and str(entry.get("id", "")).lower() != _bug_key(bug):
        return False
    haystack = " ".join(str(entry.get(f) or "")
                        for f in ("id", "title", "description", "summary")).lower()
    return all(word.lower() in haystack for word in words)


def format_line(entry):
    """One search result: '<id> [<kind>] <dlls or dll> — <title>'."""
    kind = entry.get("kind", "")
    if kind == "variant":
        dll = str(entry.get("dll", ""))
        title = entry.get("title") or " ".join(
            str(entry[f]) for f in ("dll", "provider", "version", "arch") if entry.get(f))
    else:
        dll = ", ".join(str(d) for d in entry.get("dlls") or [])
        title = entry.get("title", "")
    return "%s [%s] %s — %s" % (entry.get("id", ""), kind, dll, title)


def format_field(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(format_field(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)


def find_entry(entries, entry_id):
    wanted = str(entry_id).strip().lower()
    for entry in entries:
        if str(entry.get("id", "")).lower() == wanted:
            return entry
    return None


def cmd_search(args):
    entries = load_index(catalog_source())
    found = [e for e in entries if match(e, args.program, args.dll, args.bug, args.text)]
    if not found:
        print("no matching entries")
        return 1
    for entry in found:
        print(format_line(entry))
    return 0


def cmd_show(args):
    entry = find_entry(load_index(catalog_source()), args.id)
    if entry is None:
        raise CatalogError("no entry with id %s" % args.id)
    for key, value in entry.items():
        print("%s: %s" % (key, format_field(value)))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="catalog.py", description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="find fix and variant entries")
    s.add_argument("--program", help="exe name, for example FSViewer.exe")
    s.add_argument("--dll", help="module name, for example comctl32")
    s.add_argument("--bug", help="WineHQ bug number or entry id, for example 59609")
    s.add_argument("text", nargs="*", help="words that must all appear in id, title or description")
    sh = sub.add_parser("show", help="print all fields of one entry")
    sh.add_argument("id")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    handlers = {"search": cmd_search, "show": cmd_show}
    try:
        return handlers[args.cmd](args)
    except CatalogError as e:
        print("catalog: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
