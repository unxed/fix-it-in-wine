import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import catalog  # noqa: E402

SAMPLE = [
    {
        "id": "winehq-59609",
        "kind": "fix",
        "title": "comctl32: LVM_GETITEMPOSITION returns client coordinates in ICON views",
        "license": "LGPL-2.1-or-later",
        "bug": "https://bugs.winehq.org/show_bug.cgi?id=59609",
        "dlls": ["comctl32", "comctl32_v6"],
        "programs": ["FSViewer.exe"],
        "wine": ["wine-9.0", "wine-11.0"],
        "patch": "https://raw.githubusercontent.com/example/fix.patch",
        "patch_sha256": "4c4e4672a06370e612f9305be7cab7a59c8dd7d8638297b1029831a4d0218295",
        "ai_assisted": True,
        "path": "fixes/winehq-59609.md",
    },
    {
        "id": "winehq-12345",
        "kind": "fix",
        "title": "kernel32: GetFileAttributesEx fails on UNC paths",
        "license": "LGPL-2.1-or-later",
        "bug": "https://bugs.winehq.org/show_bug.cgi?id=12345",
        "dlls": ["kernel32"],
        "programs": ["Tool.exe", "Other.EXE"],
        "patch": "https://raw.githubusercontent.com/example/unc.patch",
        "patch_sha256": "0" * 64,
        "path": "fixes/winehq-12345.md",
    },
    {
        "id": "ucrtbase-cc580-1.0",
        "kind": "variant",
        "dll": "ucrtbase",
        "provider": "cc580",
        "version": "1.0",
        "arch": "x86_64",
        "license": "MIT",
        "source": "https://example.org/cc580.tar.xz",
        "sha256": "1" * 64,
        "path": "variants/ucrtbase-cc580-1.0.md",
    },
    {
        "id": "riched20-wine-11.0",
        "kind": "variant",
        "dll": "riched20",
        "provider": "wine",
        "version": "11.0",
        "arch": "i386",
        "title": "Wine 11.0 riched20",
        "license": "LGPL-2.1-or-later",
        "source": "https://dl.winehq.org/wine/wine-11.0.tar.xz",
        "sha256": "2" * 64,
        "path": "variants/riched20-wine-11.0.md",
    },
]


class CatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="test_catalog_")
        cls.index_path = os.path.join(cls.tmpdir, "index.json")
        with open(cls.index_path, "w", encoding="utf-8") as f:
            json.dump(SAMPLE, f)
        cls.fix = SAMPLE[0]
        cls.unc = SAMPLE[1]
        cls.variant = SAMPLE[2]
        cls.variant_titled = SAMPLE[3]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"FIW_CATALOG": self.index_path})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = catalog.main(argv)
        return code, out.getvalue(), err.getvalue()

    # load_index

    def test_load_local_index(self):
        entries = catalog.load_index(self.index_path)
        self.assertEqual([e["id"] for e in entries], [e["id"] for e in SAMPLE])

    def test_load_rejects_non_array(self):
        path = os.path.join(self.tmpdir, "object.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"id": "x"}, f)
        with self.assertRaises(catalog.CatalogError):
            catalog.load_index(path)

    def test_load_missing_file(self):
        with self.assertRaises(catalog.CatalogError):
            catalog.load_index(os.path.join(self.tmpdir, "missing.json"))

    # match

    def test_match_program(self):
        self.assertTrue(catalog.match(self.fix, program="FSViewer"))
        self.assertTrue(catalog.match(self.fix, program="fsviewer.exe"))
        self.assertTrue(catalog.match(self.unc, program="other.exe"))
        self.assertFalse(catalog.match(self.fix, program="Tool"))
        self.assertFalse(catalog.match(self.variant, program="ucrtbase"))

    def test_match_dll_with_and_without_suffix(self):
        self.assertTrue(catalog.match(self.fix, dll="comctl32"))
        self.assertTrue(catalog.match(self.fix, dll="comctl32.dll"))
        self.assertTrue(catalog.match(self.fix, dll="COMCTL32_V6.DLL"))
        self.assertFalse(catalog.match(self.fix, dll="comctl"))
        self.assertFalse(catalog.match(self.fix, dll="kernel32"))

    def test_match_dll_of_variant(self):
        self.assertTrue(catalog.match(self.variant, dll="ucrtbase.dll"))
        self.assertFalse(catalog.match(self.variant, dll="riched20"))

    def test_match_bug_number_and_id(self):
        self.assertTrue(catalog.match(self.fix, bug="59609"))
        self.assertTrue(catalog.match(self.fix, bug="winehq-59609"))
        self.assertFalse(catalog.match(self.fix, bug="12345"))
        self.assertFalse(catalog.match(self.variant, bug="59609"))

    def test_match_words(self):
        self.assertTrue(catalog.match(self.fix, words=("lvm_getitemposition", "comctl32")))
        self.assertTrue(catalog.match(self.fix, words=("ICON",)))
        self.assertTrue(catalog.match(self.fix, words=("winehq-59609",)))
        self.assertFalse(catalog.match(self.fix, words=("icon", "fastone")))
        self.assertTrue(catalog.match(self.fix))

    def test_match_combined_filters(self):
        self.assertTrue(catalog.match(self.fix, program="FSViewer.exe", dll="comctl32",
                                      bug="59609", words=("icon",)))
        self.assertFalse(catalog.match(self.fix, program="FSViewer.exe", dll="kernel32"))

    # format_line

    def test_format_fix_line(self):
        self.assertEqual(
            catalog.format_line(self.fix),
            "winehq-59609 [fix] comctl32, comctl32_v6 — "
            "comctl32: LVM_GETITEMPOSITION returns client coordinates in ICON views")

    def test_format_variant_line_without_title(self):
        self.assertEqual(
            catalog.format_line(self.variant),
            "ucrtbase-cc580-1.0 [variant] ucrtbase — ucrtbase cc580 1.0 x86_64")

    def test_format_variant_line_with_title(self):
        self.assertEqual(
            catalog.format_line(self.variant_titled),
            "riched20-wine-11.0 [variant] riched20 — Wine 11.0 riched20")

    # commands

    def test_search_all_without_filters(self):
        code, out, _ = self.run_main(["search"])
        self.assertEqual(code, 0)
        self.assertEqual(len(out.splitlines()), len(SAMPLE))

    def test_search_by_program(self):
        code, out, _ = self.run_main(["search", "--program", "FSViewer.exe"])
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [catalog.format_line(self.fix)])

    def test_search_by_dll_without_suffix(self):
        code, out, _ = self.run_main(["search", "--dll", "kernel32"])
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [catalog.format_line(self.unc)])

    def test_search_by_dll_with_suffix(self):
        code, out, _ = self.run_main(["search", "--dll", "ucrtbase.dll"])
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [catalog.format_line(self.variant)])

    def test_search_by_bug_number_and_id(self):
        for arg in ("59609", "winehq-59609"):
            code, out, _ = self.run_main(["search", "--bug", arg])
            self.assertEqual(code, 0)
            self.assertEqual(out.splitlines(), [catalog.format_line(self.fix)])

    def test_search_by_words(self):
        code, out, _ = self.run_main(["search", "UNC", "paths"])
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [catalog.format_line(self.unc)])

    def test_search_combined_filters(self):
        code, out, _ = self.run_main(["search", "--dll", "comctl32", "--bug", "59609", "icon"])
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [catalog.format_line(self.fix)])

    def test_search_no_match(self):
        code, out, err = self.run_main(["search", "--dll", "nosuchmodule"])
        self.assertEqual(code, 1)
        self.assertEqual(out.strip(), "no matching entries")
        self.assertEqual(err, "")

    def test_search_unreadable_index(self):
        with mock.patch.dict(os.environ, {"FIW_CATALOG": os.path.join(self.tmpdir, "none.json")}):
            code, out, err = self.run_main(["search", "--dll", "comctl32"])
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("catalog: "))
        self.assertNotIn("Traceback", err)

    def test_show_existing_entry(self):
        code, out, _ = self.run_main(["show", "winehq-59609"])
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertIn("id: winehq-59609", lines)
        self.assertIn("dlls: comctl32, comctl32_v6", lines)
        self.assertIn("programs: FSViewer.exe", lines)
        self.assertIn("ai_assisted: true", lines)

    def test_show_unknown_id(self):
        code, out, err = self.run_main(["show", "winehq-1"])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(err.strip(), "catalog: no entry with id winehq-1")


if __name__ == "__main__":
    unittest.main()
