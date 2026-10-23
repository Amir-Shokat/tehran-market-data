"""Normalising Persian names in FIPIRAN and TSETMC data.

The same firm appears under several spellings (Arabic vs Persian letters, missing or extra
spaces, legal-form suffixes, role prefixes such as "مدیر (...)"). Without normalisation one
manager can look like three, which breaks any count or concentration measure.
"""

from __future__ import annotations

import re

_LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "‏": "", "‎": "", "﻿": ""})

# role wrappers: "مدیر (X)" -> "X", "حسابرس (X)" -> "X", "متولی (X)" -> "X"
_ROLE_WRAPPERS = [re.compile(rf"^\s*{w}\s*\((.*)\)\s*$") for w in ("مدیر", "حسابرس", "متولی", "ضامن")]
_RULES = [
    (re.compile(r"\s*\(\s*سهامی\s+(خاص|عام)\s*\)"), ""),   # legal form in brackets
    (re.compile(r"\s*سهامی\s+(خاص|عام)\s*$"), ""),          # legal form at the end
    (re.compile(r"سرمایه\s*گذاری"), "سرمایه‌گذاری"),   # one spelling, with a half-space
    (re.compile(r"سبد\s+گردان"), "سبدگردان"),
    (re.compile(r"نو\s+ویرا"), "نوویرا"),
    (re.compile(r"(مشاور)(سرمایه‌گذاری)"), r"\1 \2"),
    (re.compile(r"\s*،\s*مدیر\s*$"), ""),                   # trailing ", manager"
]
_PLACEHOLDERS = {"", "nan", "None", "نامشخص", "نامشخصنامشخص"}


def normalize_persian(value):
    """Unify Arabic/Persian letters, drop direction marks, collapse whitespace."""
    if not isinstance(value, str):
        return value
    return " ".join(value.translate(_LETTERS).split())


def clean_firm_name(value):
    """Canonical firm name for managers, guarantors, custodians and auditors.

    Returns None for empty or placeholder values ("نامشخص" = unknown).
    """
    if not isinstance(value, str):
        return None
    s = normalize_persian(value)
    for wrapper in _ROLE_WRAPPERS:
        m = wrapper.match(s)
        if m:
            s = m.group(1)
            break
    for pattern, repl in _RULES:
        s = pattern.sub(repl, s)
    s = " ".join(s.split())
    return None if s in _PLACEHOLDERS else s
