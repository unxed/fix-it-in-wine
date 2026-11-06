#!/usr/bin/env python3
"""Read-only client for the WineHQ Bugzilla REST API.

  winebugs.py search TERMS... [--limit 20]
  winebugs.py show ID [--comments N] [--width W]
  winebugs.py attachments ID [--all]
  winebugs.py get-attachment ATT_ID -o FILE

Environment: FIW_BUGZILLA (REST base, default https://bugs.winehq.org/rest).
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

FIELDS = "id,summary,status,resolution,component,last_change_time"


class BugsError(Exception):
    pass


def base_url():
    return os.environ.get("FIW_BUGZILLA", "https://bugs.winehq.org/rest").rstrip("/")


def search_url(base, terms, limit):
    query = urllib.parse.urlencode(
        {"quicksearch": " ".join(terms), "include_fields": FIELDS, "limit": limit},
        safe=",")
    return "%s/bug?%s" % (base.rstrip("/"), query)


def bug_url(base, bug_id):
    return "%s/bug/%d?include_fields=%s" % (base.rstrip("/"), bug_id, FIELDS)


def format_bug(bug):
    status = bug.get("status", "")
    if bug.get("resolution"):
        status += "/" + bug["resolution"]
    return "%s %s %s %s  %s" % (bug.get("id"), status, bug.get("component", ""),
                                (bug.get("last_change_time") or "")[:10],
                                bug.get("summary", ""))


def truncate(text, width):
    """One-line text, cut to width characters."""
    text = " ".join((text or "").split())
    return text if len(text) <= width else text[:max(0, width - 1)] + "\u2026"


def format_comment(c, width):
    return "#%s %s %s: %s" % (c.get("count"), c.get("creator", ""),
                              (c.get("creation_time") or "")[:10],
                              truncate(c.get("text", ""), width))


def parse_attachments(obj, bug_id, include_obsolete=False):
    """Attachment dicts of a /bug/<id>/attachment response, obsolete ones optional."""
    items = (obj.get("bugs") or {}).get(str(bug_id)) or []
    return [a for a in items if include_obsolete or not a.get("is_obsolete")]


def format_attachment(a):
    flags = ""
    if a.get("is_patch"):
        flags += "[patch] "
    if a.get("is_obsolete"):
        flags += "[obsolete] "
    return "%s %s%s \u2014 %s" % (a.get("id"), flags, a.get("file_name", ""),
                                  a.get("summary", ""))


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "fix-it-in-wine",
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("message")
        except Exception:
            msg = None
        raise BugsError("HTTP %d from %s%s" % (e.code, url, ": " + msg if msg else ""))
    except (urllib.error.URLError, OSError) as e:
        raise BugsError("cannot reach %s: %s" % (url, getattr(e, "reason", e)))
    except ValueError:
        raise BugsError("%s did not return JSON" % url)


def cmd_search(args):
    obj = fetch_json(search_url(base_url(), args.terms, args.limit))
    bugs = obj.get("bugs") or []
    for bug in bugs:
        print(format_bug(bug))
    if not bugs:
        print("no bugs found")
    return 0


def cmd_show(args):
    base = base_url()
    bugs = fetch_json(bug_url(base, args.id)).get("bugs") or []
    if not bugs:
        raise BugsError("bug %d not found" % args.id)
    print(format_bug(bugs[0]))
    obj = fetch_json("%s/bug/%d/comment" % (base, args.id))
    comments = ((obj.get("bugs") or {}).get(str(args.id)) or {}).get("comments") or []
    if comments:
        print(format_comment(comments[0], args.width))   # comment 0 is the description
    rest = comments[1:]
    if args.comments > 0:
        for c in rest[-args.comments:]:
            print(format_comment(c, args.width))
    return 0


def cmd_attachments(args):
    obj = fetch_json("%s/bug/%d/attachment?exclude_fields=data" % (base_url(), args.id))
    atts = parse_attachments(obj, args.id, args.all)
    for a in atts:
        print(format_attachment(a))
    if not atts:
        print("no attachments")
    return 0


def cmd_get_attachment(args):
    # Standard Bugzilla 5 response; not checked against bugs.winehq.org yet.
    obj = fetch_json("%s/bug/attachment/%d" % (base_url(), args.att_id))
    att = (obj.get("attachments") or {}).get(str(args.att_id))
    if not att or "data" not in att:
        raise BugsError("attachment %d not found or has no data" % args.att_id)
    data = base64.b64decode(att["data"])
    try:
        with open(args.output, "wb") as f:
            f.write(data)
    except OSError as e:
        raise BugsError("cannot write %s: %s" % (args.output, e.strerror or e))
    print("%s: %d bytes (%s)" % (args.output, len(data), att.get("file_name", "")))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="winebugs.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="quick search")
    s.add_argument("terms", nargs="+")
    s.add_argument("--limit", type=int, default=20)
    sh = sub.add_parser("show", help="bug summary, description and last comments")
    sh.add_argument("id", type=int)
    sh.add_argument("--comments", type=int, default=3)
    sh.add_argument("--width", type=int, default=600)
    at = sub.add_parser("attachments", help="list attachments of a bug")
    at.add_argument("id", type=int)
    at.add_argument("--all", action="store_true", help="include obsolete attachments")
    ga = sub.add_parser("get-attachment", help="download one attachment")
    ga.add_argument("att_id", type=int)
    ga.add_argument("-o", "--output", required=True)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    handlers = {"search": cmd_search, "show": cmd_show, "attachments": cmd_attachments,
                "get-attachment": cmd_get_attachment}
    try:
        return handlers[args.cmd](args)
    except BugsError as e:
        print("winebugs: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
