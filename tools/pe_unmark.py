#!/usr/bin/env python3
"""Clear the Wine builtin mark in a PE file.

Wine's load_builtin() treats a file carrying the builtin mark as its own
builtin module and loads that instead. With the mark cleared, the file is
loaded as a native DLL.
"""

import argparse
import struct
import sys

MARK_OFF = 0x40
MARK_LEN = 0x20
BUILTIN = b"Wine builtin DLL"
PLACEHOLDER = b"Wine placeholder DLL"
MACHINES = {0x14C: "i386", 0x8664: "x86_64"}


class NotPE(ValueError):
    """The data is not a PE file."""


class Placeholder(ValueError):
    """A Wine placeholder DLL; it has no code."""


def _e_lfanew(data):
    if len(data) < 0x60 or data[:2] != b"MZ":
        raise NotPE("not a PE file")
    return struct.unpack_from("<I", data, 0x3C)[0]


def _padded(text):
    return text + b"\0" * (MARK_LEN - len(text))


def mark_of(data):
    """Return "builtin", "placeholder" or "none"."""
    if _e_lfanew(data) < 0x60:
        return "none"
    field = bytes(data[MARK_OFF:MARK_OFF + MARK_LEN])
    if field == _padded(BUILTIN):
        return "builtin"
    if field == _padded(PLACEHOLDER):
        return "placeholder"
    return "none"


def unmark(data):
    """Return the data with the builtin mark zeroed (unchanged if no mark)."""
    kind = mark_of(data)
    if kind == "placeholder":
        raise Placeholder("placeholder DLL has no code")
    if kind == "none":
        return bytes(data)
    out = bytearray(data)
    out[MARK_OFF:MARK_OFF + MARK_LEN] = bytes(MARK_LEN)
    return bytes(out)


def pe_machine(data):
    """Return "i386", "x86_64" or "other:0x...." for the PE header."""
    e_lfanew = _e_lfanew(data)
    if e_lfanew + 6 > len(data) or data[e_lfanew:e_lfanew + 4] != b"PE\0\0":
        raise NotPE("no PE signature")
    machine = struct.unpack_from("<H", data, e_lfanew + 4)[0]
    return MACHINES.get(machine, f"other:0x{machine:04x}")


def pe_export_name(data):
    """Name in the export directory (e.g. "comctl32_v6.dll"), or None if there is none.

    Wine 11 builds common controls 6 as a separate module, comctl32_v6, whose winsxs copy is
    named comctl32.dll: the export name tells which module a file really is.
    """
    e_lfanew = _e_lfanew(data)
    try:
        if data[e_lfanew:e_lfanew + 4] != b"PE\0\0":
            raise NotPE("no PE signature")
        nsec, = struct.unpack_from("<H", data, e_lfanew + 6)
        optsz, = struct.unpack_from("<H", data, e_lfanew + 20)
        opt = e_lfanew + 24
        magic, = struct.unpack_from("<H", data, opt)
        rva, _size = struct.unpack_from("<II", data, opt + (96 if magic == 0x10B else 112))
        if not rva:
            return None
        sections = [struct.unpack_from("<8sIIII", data, opt + optsz + i * 40) for i in range(nsec)]

        def offset(r):
            for _name, vsize, va, rawsize, rawptr in sections:
                if va <= r < va + max(vsize, rawsize) and r - va < rawsize:
                    return rawptr + r - va
            return None

        exp = offset(rva)
        if exp is None:
            return None
        name = offset(struct.unpack_from("<I", data, exp + 12)[0])
        if name is None:
            return None
        return data[name:data.index(b"\0", name)].decode("ascii", "replace")
    except (struct.error, ValueError) as e:
        raise NotPE("broken PE headers: %s" % e)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Clear the Wine builtin mark of a PE file.")
    ap.add_argument("src")
    ap.add_argument("dst")
    args = ap.parse_args(argv)

    try:
        with open(args.src, "rb") as f:
            data = f.read()
        kind = mark_of(data)
        out = unmark(data)  # raises Placeholder for placeholder DLLs
    except (NotPE, Placeholder) as e:
        print(f"error: {args.src}: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    try:
        with open(args.dst, "wb") as f:
            f.write(out)
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if kind == "builtin":
        print(f"{args.dst}: mark cleared")
    else:
        print(f"{args.dst}: no builtin mark, copied as is")
    return 0


if __name__ == "__main__":
    sys.exit(main())
