# -*- coding: utf-8 -*-
"""Single source of truth for the Persian font used by PDF exports.

Every PDF export used to resolve its own font, and all of them looked only at
C:\\Windows\\Fonts. The Vazirmatn face that the build bundles into the EXE was
therefore never used for PDFs, and on a server without Tahoma the exports fell
back to Helvetica, which has no Persian glyphs at all. Resolution now happens
here once: the bundled Vazirmatn first, the Windows fonts only as a fallback.
"""
import os
import sys

REGULAR_NAME = 'Vazirmatn-Regular.ttf'
BOLD_NAME = 'Vazirmatn-Bold.ttf'
DEFAULT_FONT_NAME = 'TaskHubFa'
# Kept as a last resort only. Both cover Persian, but neither ships with the
# application, so a bare Windows Server can be missing them entirely.
_SYSTEM_FALLBACKS = (r'C:\Windows\Fonts\tahoma.ttf', r'C:\Windows\Fonts\arial.ttf')


def asset_dirs():
    """Directories that can hold files shipped alongside the application."""
    if getattr(sys, 'frozen', False):
        bundle = getattr(sys, '_MEIPASS', '')
        return [d for d in (os.path.join(bundle, 'web') if bundle else '',
                            os.path.dirname(sys.executable)) if d]
    return [os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')]


def _find(filename):
    for directory in asset_dirs():
        candidate = os.path.join(directory, filename)
        if os.path.isfile(candidate):
            return candidate
    return None


def font_files():
    """Return (regular, bold) paths. Bold is None when only one face exists."""
    regular = _find(REGULAR_NAME)
    if regular:
        return regular, _find(BOLD_NAME)
    for path in _SYSTEM_FALLBACKS:
        if os.path.isfile(path):
            return path, None
    return None, None


def register(base_name=DEFAULT_FONT_NAME):
    """Register the Persian font with reportlab and return the name to use.

    Returns 'Helvetica' only when no usable TrueType face exists anywhere; the
    export then still produces a file instead of raising, which is why the
    caller must never assume Persian glyphs are available.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    regular, bold = font_files()
    if not regular:
        return 'Helvetica'
    registered = pdfmetrics.getRegisteredFontNames()
    if base_name not in registered:
        try:
            pdfmetrics.registerFont(TTFont(base_name, regular))
        except Exception:
            return 'Helvetica'
    bold_name = base_name + '-Bold'
    if bold and bold_name not in registered:
        # Registering the family makes <b> inside a Paragraph use the real bold
        # face instead of reportlab's smeared synthetic bold.
        try:
            pdfmetrics.registerFont(TTFont(bold_name, bold))
            pdfmetrics.registerFontFamily(base_name, normal=base_name,
                                          bold=bold_name, italic=base_name,
                                          boldItalic=bold_name)
        except Exception:
            pass
    return base_name
