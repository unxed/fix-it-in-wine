import contextlib
import hashlib
import io
import os
import stat
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import override  # noqa: E402

I386, X86_64 = 0x14C, 0x8664
KEY = "HKCU\\Software\\Wine\\AppDefaults\\%s\\DllOverrides"


def fake_pe(machine, tail, builtin=True):
    """MZ, e_lfanew=0x60, builtin mark at 0x40, PE signature + machine at 0x60."""
    b = bytearray(0x200)
    b[0:2] = b"MZ"
    struct.pack_into("<I", b, 0x3C, 0x60)
    if builtin:
        b[0x40:0x40 + 16] = b"Wine builtin DLL"
    b[0x60:0x64] = b"PE\0\0"
    struct.pack_into("<H", b, 0x64, machine)
    b[0x100:0x100 + len(tail)] = tail
    return bytes(b)


def unmarked(data):
    b = bytearray(data)
    b[0x40:0x60] = bytes(32)
    return bytes(b)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class OverrideTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = self.tmp.name
        self.prefix = os.path.join(t, "pfx")
        self.sysdir = os.path.join(self.prefix, "drive_c", "windows", "syswow64")
        os.makedirs(self.sysdir)
        self.write_reg("#arch=win64\n")
        self.orig = fake_pe(I386, b"original")
        self.dest = os.path.join(self.sysdir, "comctl32.dll")
        with open(self.dest, "wb") as f:
            f.write(self.orig)
        self.new = fake_pe(I386, b"new-build")
        self.dll = self.make_file("new/comctl32.dll", self.new)
        self.log = os.path.join(t, "wine.log")
        self.install_wine("")

    def write_reg(self, text):
        with open(os.path.join(self.prefix, "system.reg"), "w") as f:
            f.write(text)

    def make_file(self, rel, data):
        path = os.path.join(self.tmp.name, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def install_wine(self, query_output):
        """Fake wine: logs its arguments; `reg query` prints query_output, exit 1 if empty."""
        script = os.path.join(self.tmp.name, "fake-wine")
        qrc = 0 if query_output else 1
        with open(script, "w") as f:
            f.write("#!/bin/sh\n"
                    "printf '%%s\\n' \"$*\" >> '%s'\n"
                    "if [ \"$1 $2\" = \"reg query\" ]; then\n"
                    "  printf '%%s' '%s'\n"
                    "  exit %d\n"
                    "fi\n"
                    "exit 0\n" % (self.log, query_output, qrc))
        os.chmod(script, 0o755)
        patcher = mock.patch.dict(os.environ, {"FIW_WINE": script})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_tool(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = override.main(list(args))
        return rc, out.getvalue(), err.getvalue()

    def apply(self, exe="app.exe", dll=None, *extra):
        return self.run_tool("apply", "--prefix", self.prefix, "--exe", exe,
                             "--dll", dll or self.dll, *extra)

    def undo(self, exe="app.exe", name="comctl32", *extra):
        return self.run_tool("undo", "--prefix", self.prefix, "--exe", exe,
                             "--name", name, *extra)

    def wine_calls(self):
        try:
            with open(self.log) as f:
                return f.read().splitlines()
        except FileNotFoundError:
            return []

    def read(self, path):
        with open(path, "rb") as f:
            return f.read()

    # ---- cases ----

    def test_apply_writes_unmarked_bytes_backup_and_registry(self):
        rc, out, err = self.apply()
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.read(self.dest), unmarked(self.new))
        backup = os.path.join(self.prefix, "fix-it-in-wine", "backup", sha(self.orig))
        self.assertEqual(self.read(backup), self.orig)
        calls = self.wine_calls()
        self.assertIn("reg add %s /v comctl32 /d native,builtin /f" % (KEY % "app.exe"), calls)
        self.assertIn("to undo:", out)
        self.assertIn("--exe app.exe --name comctl32.dll", out)

    def test_undo_restores_and_deletes_registry_value(self):
        self.apply()
        rc, out, err = self.undo()
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.read(self.dest), self.orig)
        self.assertIn("reg delete %s /v comctl32 /f" % (KEY % "app.exe"), self.wine_calls())
        rc, out, _ = self.run_tool("status", "--prefix", self.prefix)
        self.assertIn("no entries", out)

    def test_undo_restores_previous_registry_value(self):
        self.install_wine("    comctl32    REG_SZ    builtin\n")
        self.apply()
        rc, _, err = self.undo("app.exe", "comctl32.dll")
        self.assertEqual(rc, 0, err)
        self.assertIn("reg add %s /v comctl32 /d builtin /f" % (KEY % "app.exe"), self.wine_calls())

    def test_second_apply_refused(self):
        self.assertEqual(self.apply()[0], 0)
        rc, _, err = self.apply()
        self.assertNotEqual(rc, 0)
        self.assertIn("already applied, undo first", err)

    def test_conflict_between_exes(self):
        self.apply("one.exe")
        other = self.make_file("other/comctl32.dll", fake_pe(I386, b"different"))
        rc, _, err = self.apply("two.exe", other)
        self.assertNotEqual(rc, 0)
        self.assertIn("one.exe", err)
        self.assertEqual(self.read(self.dest), unmarked(self.new))

    def test_same_dll_shared_between_exes(self):
        self.apply("one.exe")
        rc, out, err = self.apply("two.exe")
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.undo("one.exe")[0], 0)
        self.assertEqual(self.read(self.dest), unmarked(self.new))
        self.assertEqual(self.undo("two.exe")[0], 0)
        self.assertEqual(self.read(self.dest), self.orig)

    def test_changed_file_needs_force(self):
        self.apply()
        with open(self.dest, "wb") as f:
            f.write(b"someone else")
        rc, _, err = self.undo()
        self.assertNotEqual(rc, 0)
        self.assertIn("file changed outside fix-it-in-wine", err)
        self.assertEqual(self.read(self.dest), b"someone else")
        rc, _, err = self.undo("app.exe", "comctl32", "--force")
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.read(self.dest), self.orig)

    def test_status_reports_changed(self):
        self.apply()
        self.assertIn("(ok)", self.run_tool("status", "--prefix", self.prefix)[1])
        with open(self.dest, "wb") as f:
            f.write(b"x")
        self.assertIn("(changed)", self.run_tool("status", "--prefix", self.prefix)[1])

    def test_symlink_dest_replaced_not_followed(self):
        target = self.make_file("target.dll", self.orig)
        os.unlink(self.dest)
        os.symlink(target, self.dest)
        rc, _, err = self.apply()
        self.assertEqual(rc, 0, err)
        self.assertFalse(os.path.islink(self.dest))
        self.assertEqual(self.read(self.dest), unmarked(self.new))
        self.assertEqual(self.read(target), self.orig)

    def test_sxs_glob_no_match(self):
        os.makedirs(os.path.join(self.prefix, "drive_c", "windows", "winsxs"))
        rc, _, err = self.apply("app.exe", None, "--slot", "sxs:*comctl32*")
        self.assertNotEqual(rc, 0)
        self.assertIn("exactly one", err)

    def test_sxs_glob_two_matches(self):
        for n in ("x86_microsoft.windows.common-controls_a", "x86_microsoft.windows.common-controls_b"):
            os.makedirs(os.path.join(self.prefix, "drive_c", "windows", "winsxs", n))
        rc, _, err = self.apply("app.exe", None, "--slot", "sxs:*common-controls*")
        self.assertNotEqual(rc, 0)
        self.assertIn("common-controls_a", err)
        self.assertIn("common-controls_b", err)

    def test_sxs_glob_one_match(self):
        d = os.path.join(self.prefix, "drive_c", "windows", "winsxs", "x86_common-controls_6")
        os.makedirs(d)
        with open(os.path.join(d, "comctl32.dll"), "wb") as f:
            f.write(self.orig)
        rc, _, err = self.apply("app.exe", None, "--slot", "sxs:*common-controls*")
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.read(os.path.join(d, "comctl32.dll")), unmarked(self.new))

    def test_x86_64_dll_in_win32_prefix(self):
        self.write_reg("#arch=win32\n")
        dll = self.make_file("x64/comctl32.dll", fake_pe(X86_64, b"64"))
        rc, _, err = self.apply("app.exe", dll)
        self.assertNotEqual(rc, 0)
        self.assertIn("win32", err)

    def test_nothing_to_replace(self):
        os.unlink(self.dest)
        rc, _, err = self.apply()
        self.assertNotEqual(rc, 0)
        self.assertIn("nothing to replace at " + self.dest, err)

    def test_not_a_pe(self):
        rc, _, err = self.apply("app.exe", self.make_file("junk.dll", b"junk"))
        self.assertNotEqual(rc, 0)
        self.assertNotIn("Traceback", err)

    def test_slot_dirs(self):
        p = "/p"
        w = "/p/drive_c/windows/"
        self.assertEqual(override.slot_dir(p, "system", "i386", "win64"), w + "syswow64")
        self.assertEqual(override.slot_dir(p, "system", "i386", "win32"), w + "system32")
        self.assertEqual(override.slot_dir(p, "system", "x86_64", "win64"), w + "system32")

    def test_parse_reg_query(self):
        text = "HKEY_CURRENT_USER\\...\n    comctl32    REG_SZ    native,builtin\n"
        self.assertEqual(override.parse_reg_query(text, "comctl32"), "native,builtin")
        self.assertIsNone(override.parse_reg_query(text, "gdi32"))


if __name__ == "__main__":
    unittest.main()
