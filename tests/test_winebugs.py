import os
import sys
import unittest
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import winebugs  # noqa: E402


class WineBugsTest(unittest.TestCase):
    def test_search_url_encoding(self):
        url = winebugs.search_url("https://bugs.winehq.org/rest/", ["comctl32", "list view & more"], 5)
        self.assertTrue(url.startswith("https://bugs.winehq.org/rest/bug?"))
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(q["quicksearch"], ["comctl32 list view & more"])
        self.assertEqual(q["limit"], ["5"])
        self.assertEqual(q["include_fields"], [winebugs.FIELDS])
        self.assertNotIn(" ", url)
        self.assertNotIn("& more", url)

    def test_format_bug(self):
        bug = {"id": 59251, "status": "UNCONFIRMED", "resolution": "", "component": "comctl32",
               "last_change_time": "2026-11-01T10:20:30Z",
               "summary": "FastStone Image Viewer: top preview list window problems"}
        self.assertEqual(
            winebugs.format_bug(bug),
            "59251 UNCONFIRMED comctl32 2026-11-01  FastStone Image Viewer: top preview list window problems")

    def test_format_bug_resolution(self):
        bug = {"id": 1, "status": "RESOLVED", "resolution": "FIXED", "component": "x",
               "last_change_time": "2026-01-02T00:00:00Z", "summary": "s"}
        self.assertTrue(winebugs.format_bug(bug).startswith("1 RESOLVED/FIXED x 2026-01-02"))

    def test_format_comment_truncates(self):
        c = {"count": 4, "creator": "a@b.c", "creation_time": "2026-05-06T01:02:03Z",
             "text": "x" * 100}
        line = winebugs.format_comment(c, 20)
        self.assertTrue(line.startswith("#4 a@b.c 2026-05-06: "))
        self.assertEqual(len(line.split(": ", 1)[1]), 20)

    def test_format_comment_single_line(self):
        c = {"count": 0, "creator": "u", "creation_time": "2026-05-06T01:02:03Z",
             "text": "one\ntwo\n\nthree"}
        self.assertTrue(winebugs.format_comment(c, 600).endswith(": one two three"))

    def test_attachment_filtering(self):
        obj = {"bugs": {"7": [
            {"id": 1, "file_name": "a.patch", "summary": "fix", "is_patch": True, "is_obsolete": False},
            {"id": 2, "file_name": "b.patch", "summary": "old fix", "is_patch": True, "is_obsolete": True},
            {"id": 3, "file_name": "c.png", "summary": "shot", "is_patch": False, "is_obsolete": False}]}}
        self.assertEqual([a["id"] for a in winebugs.parse_attachments(obj, 7, False)], [1, 3])
        self.assertEqual([a["id"] for a in winebugs.parse_attachments(obj, 7, True)], [1, 2, 3])
        self.assertEqual(winebugs.parse_attachments(obj, 8, True), [])

    def test_format_attachment(self):
        a = {"id": 2, "file_name": "b.patch", "summary": "old fix", "is_patch": True,
             "is_obsolete": True}
        self.assertEqual(winebugs.format_attachment(a), "2 [patch] [obsolete] b.patch \u2014 old fix")
        a = {"id": 3, "file_name": "c.png", "summary": "shot"}
        self.assertEqual(winebugs.format_attachment(a), "3 c.png \u2014 shot")


if __name__ == "__main__":
    unittest.main()
