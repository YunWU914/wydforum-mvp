#!/usr/bin/env python
"""Build Django gettext catalogs without GNU gettext.

Translations live in tools/locales/<locale>.json as {english: translation}.
This script:
  * extracts every {% trans %} / _("...") string from templates and Python
  * writes locale/<locale>/LC_MESSAGES/django.po
  * compiles django.mo with a small pure-Python writer
  * optionally reports missing translations (--check)

Usage:
  python tools/build_locales.py
  python tools/build_locales.py --check
  python tools/build_locales.py --list
"""

import argparse
import io
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALE_DIR = ROOT / "locale"
SOURCE_DIR = ROOT / "tools" / "locales"

LOCALES = {
    "zh_Hans": ("zh-hans", "nplurals=1; plural=0;"),
    "ja": ("ja", "nplurals=1; plural=0;"),
    "es": ("es", "nplurals=2; plural=(n != 1);"),
}

TRANS_RE = re.compile(
    r"""{%\s*(?:trans|translate)\s+(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')\s*%}"""
)
BLOCK_RE = re.compile(
    r"""{%\s*blocktrans(?:\s+[^%]*)?%}(.*?){%\s*endblocktrans\s*%}""", re.S
)
PY_RE = re.compile(
    r"""(?<![\w.])_\s*\(\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')\s*\)""",
    re.S,
)


def unescape(value: str) -> str:
    return value.replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\")


def extract():
    msgids = set()
    for path in sorted((ROOT / "templates").rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        for match in TRANS_RE.finditer(text):
            msgids.add(unescape(match.group(1) or match.group(2) or ""))
        for match in BLOCK_RE.finditer(text):
            inner = re.sub(r"\s+", " ", match.group(1)).strip()
            inner = re.sub(r"{{\s*(\w+)\s*}}", r"%(\1)s", inner)
            msgids.add(inner)
    for path in sorted((ROOT / "community").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in PY_RE.finditer(text):
            msgids.add(unescape(match.group(1) or match.group(2) or ""))
    msgids.discard("")
    return msgids


def po_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )


def write_po(path: Path, locale: str, messages: dict):
    lines = [
        'msgid ""',
        'msgstr ""',
        '"Project-Id-Version: OpenForum MVP\\n"',
        '"Report-Msgid-Bugs-To: \\n"',
        '"MIME-Version: 1.0\\n"',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '"Content-Transfer-Encoding: 8bit\\n"',
        f'"Language: {locale}\\n"',
        f'"Plural-Forms: {LOCALES[locale][1]}\\n"',
        "",
    ]
    for msgid in sorted(messages):
        lines.append(f'msgid "{po_escape(msgid)}"')
        lines.append(f'msgstr "{po_escape(messages[msgid])}"')
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_mo(path: Path, locale: str, messages: dict):
    header = (
        "Project-Id-Version: OpenForum MVP\n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=UTF-8\n"
        "Content-Transfer-Encoding: 8bit\n"
        f"Language: {locale}\n"
        f"Plural-Forms: {LOCALES[locale][1]}\n"
    )
    entries = [("", header)] + [(key, value) for key, value in messages.items()]
    entries.sort(key=lambda item: item[0].encode("utf-8"))

    ids = b""
    strs = b""
    id_table = []
    str_table = []
    for msgid, msgstr in entries:
        mid = msgid.encode("utf-8")
        mstr = msgstr.encode("utf-8")
        id_table.append((len(mid), len(ids)))
        str_table.append((len(mstr), len(strs)))
        ids += mid + b"\0"
        strs += mstr + b"\0"

    count = len(entries)
    orig_offset = 28
    trans_offset = orig_offset + count * 8
    ids_offset = trans_offset + count * 8
    strs_offset = ids_offset + len(ids)

    out = io.BytesIO()
    out.write(struct.pack("<Iiiiiii", 0x950412DE, 0, count, orig_offset, trans_offset, 0, 0))
    # Offsets in a .mo file are absolute (from the start of the file).
    for length, offset in id_table:
        out.write(struct.pack("<ii", length, ids_offset + offset))
    for length, offset in str_table:
        out.write(struct.pack("<ii", length, strs_offset + offset))
    out.write(ids)
    out.write(strs)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out.getvalue())


def load_catalog(locale: str) -> dict:
    path = SOURCE_DIR / f"{locale}.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {key: value for key, value in data.items() if isinstance(value, str) and value}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Report missing strings.")
    parser.add_argument("--list", action="store_true", help="Print all msgids.")
    args = parser.parse_args()

    msgids = extract()
    if args.list:
        for msgid in sorted(msgids):
            print(msgid)
        return 0

    missing_total = 0
    for locale in LOCALES:
        messages = load_catalog(locale)
        missing = sorted(msgids - set(messages))
        extra = sorted(set(messages) - msgids)
        if args.check:
            print(f"{locale}: {len(messages)} entries, {len(missing)} missing")
            for msgid in missing:
                print(f"  missing: {msgid}")
            for msgid in extra:
                print(f"  unused:  {msgid}")
            missing_total += len(missing)
            continue

        write_po(LOCALE_DIR / locale / "LC_MESSAGES" / "django.po", locale, messages)
        write_mo(LOCALE_DIR / locale / "LC_MESSAGES" / "django.mo", locale, messages)
        print(f"{locale}: {len(messages)} strings -> django.po / django.mo")

    if args.check:
        return 1 if missing_total else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
