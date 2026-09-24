"""Best-effort mapping from an extracted PDF font to one of PyMuPDF's built-in
base-14 fonts, used when re-inserting text after a redaction.

Exact reproduction of an original embedded font isn't possible when inserting
brand-new glyphs (see the "known limitations" section of the PDF Editor spec),
so this picks the closest built-in family/weight/style by name + span flags.
"""

FLAG_ITALIC = 1 << 1
FLAG_SERIFED = 1 << 2
FLAG_MONOSPACED = 1 << 3
FLAG_BOLD = 1 << 4


def is_bold(font_name, flags=0):
    return bool(flags & FLAG_BOLD) or 'bold' in (font_name or '').lower()


def is_italic(font_name, flags=0):
    name = (font_name or '').lower()
    return bool(flags & FLAG_ITALIC) or 'italic' in name or 'oblique' in name


def base14_font(font_name, flags=0):
    """Return a PyMuPDF built-in fontname (e.g. 'helv', 'hebo', 'tibi', 'cour')."""
    name = (font_name or '').lower()
    bold = is_bold(font_name, flags)
    italic = is_italic(font_name, flags)
    monospaced = bool(flags & FLAG_MONOSPACED) or 'mono' in name or 'courier' in name or 'consol' in name
    serifed = bool(flags & FLAG_SERIFED) or any(s in name for s in ('times', 'georgia', 'serif', 'garamond', 'cambria'))

    if monospaced:
        family = 'cour'
        if bold and italic:
            return 'cobi'
        if bold:
            return 'cobo'
        if italic:
            return 'coit'
        return family
    if serifed:
        if bold and italic:
            return 'tibi'
        if bold:
            return 'tibo'
        if italic:
            return 'tiit'
        return 'tiro'
    # default: Helvetica family (sans)
    if bold and italic:
        return 'hebi'
    if bold:
        return 'hebo'
    if italic:
        return 'heit'
    return 'helv'


def normalize_color(color_int):
    """PyMuPDF span 'color' is a packed RGB int; convert to a 0-1 float tuple."""
    if color_int is None:
        return (0, 0, 0)
    r = ((color_int >> 16) & 255) / 255.0
    g = ((color_int >> 8) & 255) / 255.0
    b = (color_int & 255) / 255.0
    return (r, g, b)
