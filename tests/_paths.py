# -*- coding: utf-8 -*-
"""Shared project paths for the test suite.

Importing this module also puts ``src`` and ``scripts`` on ``sys.path`` so the
tests can import application modules and maintenance scripts directly.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
WEB = SRC / "web"
SCRIPTS = ROOT / "scripts"

for _path in (SCRIPTS, SRC):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# Where a bare file name such as "rbac.py" or "ui.html" is looked up.
SEARCH_DIRS = (SRC, WEB, SCRIPTS, ROOT / "config", ROOT, ROOT / "docs", ROOT / "docs" / "history")


def project_file(name):
    """Return the path of a project file given its name or root-relative path."""
    if "/" in name or "\\" in name:
        return ROOT / name
    matches = [d / name for d in SEARCH_DIRS if (d / name).is_file()]
    if len(matches) > 1:
        raise LookupError("%s exists in more than one project folder: %s" % (name, matches))
    return matches[0] if matches else ROOT / name
