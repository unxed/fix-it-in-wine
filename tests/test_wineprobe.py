import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import wineprobe  # noqa: E402

SAMPLE = r'''0024:trace:loaddll:build_module Loaded L"C:\\windows\\system32\\kernel32.dll" at 00006FFFFFE40000: builtin
0024:0028:trace:loaddll:build_module Loaded L"C:\\windows\\system32\\comctl32.dll" at 000000007A000000: native
trace:loaddll:build_module Loaded L"C:\\windows\\system32\\gdi32.dll" at 0000000070000000: builtin
0024:err:module:import_dll Library FOO.dll (which is needed by L"C:\\app\\app.exe") not found
0024:err:module:import_dll Library BAR.dll (which is needed by L"C:\\app\\app.exe") not found
0024:err:ole:CoGetClassObject class {1234} not registered
0024:warn:module:LdrGetProcedureAddress No implementation for foo.dll.Bar imported from L"C:\\app\\baz.dll", setting to 0xdeadbeef
0024:warn:module:LdrGetProcedureAddress No implementation for foo.dll.Bar imported from L"C:\\app\\baz.dll", setting to 0xdeadbeef
0024:warn:module:LdrGetProcedureAddress No implementation for qux.Quux, setting to 0xdeadbeef
0024:fixme:ole:CoInitializeEx stub
0024:fixme:ole:CoInitializeEx stub again
0024:fixme:win:EnumDisplayDevicesW stub
wine: Unhandled page fault on read access to 0000000000000000 at address 00401000
'''.splitlines()


class DigestTest(unittest.TestCase):
    def digest(self, lines=SAMPLE, dlls=(), max_lines=60):
        return wineprobe.make_digest(lines, dlls, max_lines)

    def test_paths_unescaped_and_modes(self):
        out = self.digest(dlls=["comctl32", "KERNEL32.dll"])
        self.assertIn(r"dll comctl32: native C:\windows\system32\comctl32.dll", out)
        self.assertIn(r"dll KERNEL32.dll: builtin C:\windows\system32\kernel32.dll", out)

    def test_dll_not_loaded(self):
        self.assertIn("dll d3d11: not loaded", self.digest(dlls=["d3d11"]))

    def test_modules_and_native(self):
        out = self.digest()
        self.assertIn("modules: 3 loaded (1 native)", out)
        self.assertIn("native: comctl32.dll", out)

    def test_missing_imports_deduplicated(self):
        out = self.digest()
        self.assertEqual(out.count("  foo.dll.Bar (from baz.dll)"), 1)
        self.assertIn("  qux.Quux", out)

    def test_errors_deduplicated_by_channel_function(self):
        out = self.digest()
        errs = [l for l in out if l.startswith("  module:import_dll")]
        self.assertEqual(len(errs), 1)
        self.assertIn("  ole:CoGetClassObject class {1234} not registered", out)

    def test_errors_truncated(self):
        long = "0024:err:x:f " + "a" * 400
        out = self.digest([long])
        line = [l for l in out if l.startswith("  x:f")][0]
        self.assertEqual(len(line), 2 + 160)

    def test_fixme_counting(self):
        out = self.digest()
        self.assertIn("  ole:CoInitializeEx x2", out)
        self.assertIn("  win:EnumDisplayDevicesW x1", out)
        self.assertLess(out.index("  ole:CoInitializeEx x2"),
                        out.index("  win:EnumDisplayDevicesW x1"))

    def test_unhandled_exception_line_without_debug_prefix(self):
        out = self.digest()
        self.assertIn("exceptions:", out)
        self.assertTrue(any("Unhandled page fault" in l for l in out))

    def test_max_lines_cap(self):
        many = ["0024:err:chan:func%d message" % i for i in range(30)]
        out = self.digest(many, max_lines=5)
        self.assertEqual(len(out), 5)
        self.assertTrue(out[-1].startswith("..."))

    def test_prefix_forms_parse(self):
        for line in ("err:a:b msg", "0024:err:a:b msg", "0024:0028:err:a:b msg"):
            self.assertIn("  a:b msg", self.digest([line]))

    def test_presets(self):
        self.assertEqual(wineprobe.debug_string(), "+loaddll,warn+module")
        self.assertEqual(wineprobe.debug_string("crash"), "+loaddll,+seh,warn+module")
        self.assertEqual(wineprobe.debug_string("channels:relay,seh"),
                         "+loaddll,warn+module,+relay,+seh")
        self.assertEqual(wineprobe.debug_string(debug="err+all"), "err+all")
        with self.assertRaises(wineprobe.ProbeError):
            wineprobe.debug_string("nope")

    def test_cli_digest(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.log")
            with open(path, "w") as f:
                f.write("\n".join(SAMPLE))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = wineprobe.main(["digest", path, "--dll", "comctl32"])
        self.assertEqual(rc, 0)
        self.assertIn("dll comctl32: native", out.getvalue())

    def test_cli_missing_log(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = wineprobe.main(["digest", "/nonexistent/x.log"])
        self.assertEqual(rc, 1)
        self.assertIn("cannot read log", err.getvalue())


if __name__ == "__main__":
    unittest.main()
