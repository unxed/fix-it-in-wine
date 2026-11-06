#!/usr/bin/env python3
"""Tests for tools/pe_unmark.py (no network, no Wine)."""

import contextlib
import io
import os
import struct
import sys
import tempfile
import unittest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
sys.path.insert(0, TOOLS)
import pe_unmark  # noqa: E402


def make_pe(mark=b"", machine=0x8664, e_lfanew=0x60):
    """Fake PE: MZ header, mark at 0x40, PE signature and machine, trailing bytes."""
    head = bytearray(0x60)
    head[0:2] = b"MZ"
    struct.pack_into("<I", head, 0x3C, e_lfanew)
    head[0x40:0x40 + len(mark)] = mark
    body = b"PE\0\0" + struct.pack("<H", machine) + bytes(range(1, 65))
    return bytes(head) + body


BUILTIN = b"Wine builtin DLL"
PLACEHOLDER = b"Wine placeholder DLL"


class MarkTests(unittest.TestCase):
    def test_builtin_detected(self):
        self.assertEqual(pe_unmark.mark_of(make_pe(BUILTIN)), "builtin")

    def test_placeholder_detected(self):
        self.assertEqual(pe_unmark.mark_of(make_pe(PLACEHOLDER)), "placeholder")

    def test_no_mark(self):
        self.assertEqual(pe_unmark.mark_of(make_pe()), "none")

    def test_small_e_lfanew_is_none(self):
        self.assertEqual(pe_unmark.mark_of(make_pe(BUILTIN, e_lfanew=0x40)), "none")

    def test_short_or_garbage_raises_notpe(self):
        for data in (b"MZ", bytes(0x5F), bytes(0x100), b"\x7fELF" + bytes(200)):
            with self.subTest(data=data[:8]):
                with self.assertRaises(pe_unmark.NotPE):
                    pe_unmark.mark_of(data)


class UnmarkTests(unittest.TestCase):
    def test_only_mark_bytes_change(self):
        orig = make_pe(BUILTIN)
        out = pe_unmark.unmark(orig)
        self.assertEqual(len(out), len(orig))
        self.assertEqual(out[0x40:0x60], bytes(32))
        self.assertEqual(out[:0x40], orig[:0x40])
        self.assertEqual(out[0x60:], orig[0x60:])
        self.assertEqual(pe_unmark.mark_of(out), "none")

    def test_idempotent(self):
        once = pe_unmark.unmark(make_pe(BUILTIN))
        self.assertEqual(pe_unmark.unmark(once), once)

    def test_none_unchanged(self):
        data = make_pe()
        self.assertEqual(pe_unmark.unmark(data), data)

    def test_placeholder_raises(self):
        with self.assertRaises(pe_unmark.Placeholder):
            pe_unmark.unmark(make_pe(PLACEHOLDER))

    def test_garbage_raises_notpe(self):
        with self.assertRaises(pe_unmark.NotPE):
            pe_unmark.unmark(b"not a pe file at all, definitely more than 0x60 bytes" * 3)


class MachineTests(unittest.TestCase):
    def test_i386(self):
        self.assertEqual(pe_unmark.pe_machine(make_pe(machine=0x14C)), "i386")

    def test_x86_64(self):
        self.assertEqual(pe_unmark.pe_machine(make_pe(machine=0x8664)), "x86_64")

    def test_other(self):
        self.assertEqual(pe_unmark.pe_machine(make_pe(machine=0xAA64)), "other:0xaa64")

    def test_missing_signature_raises_notpe(self):
        data = bytearray(make_pe())
        data[0x60:0x64] = b"XX\0\0"
        with self.assertRaises(pe_unmark.NotPE):
            pe_unmark.pe_machine(bytes(data))

    def test_garbage_raises_notpe(self):
        with self.assertRaises(pe_unmark.NotPE):
            pe_unmark.pe_machine(b"garbage")


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.src = os.path.join(self.dir, "src.dll")
        self.dst = os.path.join(self.dir, "dst.dll")

    def tearDown(self):
        self._tmp.cleanup()

    def write_src(self, data):
        with open(self.src, "wb") as f:
            f.write(data)

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = pe_unmark.main(list(args))
        return rc, out.getvalue(), err.getvalue()

    def test_builtin_cleared(self):
        data = make_pe(BUILTIN)
        self.write_src(data)
        rc, out, _ = self.run_cli(self.src, self.dst)
        self.assertEqual(rc, 0)
        self.assertIn(f"{self.dst}: mark cleared", out)
        with open(self.dst, "rb") as f:
            self.assertEqual(f.read(), pe_unmark.unmark(data))

    def test_no_mark_copied(self):
        data = make_pe()
        self.write_src(data)
        rc, out, _ = self.run_cli(self.src, self.dst)
        self.assertEqual(rc, 0)
        self.assertIn(f"{self.dst}: no builtin mark, copied as is", out)
        with open(self.dst, "rb") as f:
            self.assertEqual(f.read(), data)

    def test_placeholder_exit_2(self):
        self.write_src(make_pe(PLACEHOLDER))
        rc, _, err = self.run_cli(self.src, self.dst)
        self.assertEqual(rc, 2)
        self.assertNotIn("Traceback", err)
        self.assertFalse(os.path.exists(self.dst))

    def test_not_pe_exit_2(self):
        self.write_src(b"plain text")
        rc, _, err = self.run_cli(self.src, self.dst)
        self.assertEqual(rc, 2)
        self.assertNotIn("Traceback", err)
        self.assertFalse(os.path.exists(self.dst))

    def test_missing_source_exit_1(self):
        rc, _, err = self.run_cli(os.path.join(self.dir, "missing.dll"), self.dst)
        self.assertEqual(rc, 1)
        self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()


class TestExportName(unittest.TestCase):
    def build(self, name):
        import struct
        d = bytearray(0x400)
        d[0:2] = b"MZ"; struct.pack_into("<I", d, 0x3C, 0x60)
        d[0x60:0x64] = b"PE\0\0"
        struct.pack_into("<HH", d, 0x64, 0x14C, 1)          # machine, one section
        struct.pack_into("<H", d, 0x74, 0xE0)              # size of optional header
        opt = 0x78
        struct.pack_into("<H", d, opt, 0x10B)              # PE32
        struct.pack_into("<II", d, opt + 96, 0x1000, 0x28) # export directory
        sec = opt + 0xE0
        struct.pack_into("<8sIIII", d, sec, b".edata", 0x100, 0x1000, 0x100, 0x200)
        struct.pack_into("<I", d, 0x200 + 12, 0x1028)      # name RVA
        d[0x228:0x228 + len(name) + 1] = name + b"\0"
        return bytes(d)

    def test_names(self):
        self.assertEqual(pe_unmark.pe_export_name(self.build(b"comctl32_v6.dll")), "comctl32_v6.dll")
        self.assertEqual(pe_unmark.pe_export_name(self.build(b"comctl32.dll")), "comctl32.dll")

    def test_not_pe(self):
        with self.assertRaises(pe_unmark.NotPE):
            pe_unmark.pe_export_name(b"MZ" + bytes(0x100))
