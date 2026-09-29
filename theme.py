"""
Cyberpunk green theme for Silent Squid.

Call setup(root) once before building any widgets.
All color / font constants are exported for use on classic tk widgets
(Text, Listbox, Menu) that ttk.Style cannot reach.
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

# ── palette ──────────────────────────────────────────────────────────────────
BG        = "#0a0f0a"   # root / frame background
BG_INPUT  = "#030803"   # entry / text / listbox fields
BG_BTN    = "#0a2a0a"   # button resting state
BG_ACTIVE = "#0f4a18"   # button hover / active
BG_HEADER = "#010d01"   # top banner strip

FG        = "#00e83a"   # primary text
FG_DIM    = "#3a8a52"   # secondary labels / keys
FG_MUTED  = "#1a4a28"   # hints, disabled text
ACCENT    = "#00ff41"   # neon titles, focused borders

BORDER     = "#1a4a1a"
BORDER_ACT = "#00aa2a"

SEL_BG  = "#003a14"
SEL_FG  = "#00ff41"
CURSOR  = "#00ff41"


# ── fonts ─────────────────────────────────────────────────────────────────────
def _mono(size: int, bold: bool = False) -> tuple:
    """Pick best available monospace family, fall back to Courier."""
    try:
        families = {f.lower(): f for f in tkfont.families()}
    except Exception:
        families = {}
    for name in ("Consolas", "Menlo", "Courier New", "Lucida Console",
                 "Courier", "monospace"):
        hit = families.get(name.lower())
        if hit:
            return (hit, size, "bold") if bold else (hit, size)
    return ("Courier", size, "bold") if bold else ("Courier", size)


def fonts() -> dict:
    """Return font tuples after the display is available."""
    return {
        "normal":  _mono(10),
        "bold":    _mono(10, bold=True),
        "small":   _mono(9),
        "mono":    _mono(9),
        "title":   _mono(13, bold=True),
        "header":  _mono(14, bold=True),
        "sub":     _mono(9),
    }


# ── main entry point ──────────────────────────────────────────────────────────
def setup(root: tk.Tk) -> dict:
    """
    Apply theme to *root*.  Returns the font dict so gui.py can use
    the same fonts on classic tk widgets.
    """
    f = fonts()
    root.configure(bg=BG)
    _apply_ttk(root, f)
    return f


def _apply_ttk(root: tk.Tk, f: dict):
    s = ttk.Style(root)
    s.theme_use("clam")

    # ── global defaults ───────────────────────────────────────────────────────
    s.configure(".",
        background=BG,
        foreground=FG,
        font=f["normal"],
        bordercolor=BORDER,
        darkcolor=BG,
        lightcolor=BG,
        troughcolor=BG,
        focuscolor=ACCENT,
        selectbackground=SEL_BG,
        selectforeground=SEL_FG,
        insertcolor=CURSOR,
        relief="flat",
    )

    # ── frames ────────────────────────────────────────────────────────────────
    s.configure("TFrame", background=BG)

    s.configure("TLabelFrame",
        background=BG,
        bordercolor=BORDER,
        relief="solid",
        borderwidth=1,
    )
    s.configure("TLabelFrame.Label",
        background=BG,
        foreground=FG_DIM,
        font=f["bold"],
        padding=(4, 0),
    )

    # ── labels ────────────────────────────────────────────────────────────────
    s.configure("TLabel",    background=BG, foreground=FG,       font=f["normal"])
    s.configure("Dim.TLabel",  background=BG, foreground=FG_DIM,   font=f["small"])
    s.configure("Muted.TLabel", background=BG, foreground=FG_MUTED, font=f["small"])
    s.configure("Accent.TLabel", background=BG, foreground=ACCENT,  font=f["bold"])
    s.configure("Value.TLabel",  background=BG, foreground=FG,      font=f["mono"])

    # ── buttons ───────────────────────────────────────────────────────────────
    s.configure("TButton",
        background=BG_BTN,
        foreground=FG,
        font=f["bold"],
        bordercolor=BORDER,
        padding=(10, 5),
        relief="flat",
        anchor="center",
    )
    s.map("TButton",
        background=[("disabled", BG), ("active", BG_ACTIVE), ("pressed", BG_ACTIVE)],
        foreground=[("disabled", FG_MUTED), ("active", ACCENT), ("pressed", ACCENT)],
        bordercolor=[("active", BORDER_ACT), ("focus", BORDER_ACT)],
    )

    # ── entry ─────────────────────────────────────────────────────────────────
    s.configure("TEntry",
        fieldbackground=BG_INPUT,
        foreground=FG,
        insertcolor=CURSOR,
        bordercolor=BORDER,
        selectbackground=SEL_BG,
        selectforeground=SEL_FG,
        font=f["mono"],
        padding=4,
    )
    s.map("TEntry",
        bordercolor=[("focus", BORDER_ACT)],
        fieldbackground=[("readonly", BG)],
    )

    # ── spinbox ───────────────────────────────────────────────────────────────
    s.configure("TSpinbox",
        fieldbackground=BG_INPUT,
        foreground=FG,
        insertcolor=CURSOR,
        bordercolor=BORDER,
        arrowcolor=FG_DIM,
        background=BG_BTN,
        selectbackground=SEL_BG,
        selectforeground=SEL_FG,
        font=f["mono"],
        padding=(4, 3),
    )
    s.map("TSpinbox",
        bordercolor=[("focus", BORDER_ACT)],
        arrowcolor=[("active", ACCENT)],
    )

    # ── checkbutton ───────────────────────────────────────────────────────────
    s.configure("TCheckbutton",
        background=BG,
        foreground=FG_DIM,
        font=f["normal"],
        focuscolor=BG,
        indicatorcolor=BG_INPUT,
        indicatorrelief="flat",
    )
    s.map("TCheckbutton",
        background=[("active", BG)],
        foreground=[("active", FG), ("selected", FG)],
        indicatorcolor=[
            ("selected",        ACCENT),
            ("selected active", ACCENT),
            ("active",          BORDER_ACT),
            ("!selected",       BG_INPUT),
        ],
    )

    # ── notebook ──────────────────────────────────────────────────────────────
    s.configure("TNotebook",
        background=BG,
        bordercolor=BORDER,
        tabmargins=(2, 4, 0, 0),
    )
    s.configure("TNotebook.Tab",
        background=BG_BTN,
        foreground=FG_DIM,
        font=f["bold"],
        padding=(16, 6),
        bordercolor=BORDER,
    )
    s.map("TNotebook.Tab",
        background=[("selected", BG)],
        foreground=[("selected", ACCENT)],
        expand=[("selected", (2, 2, 2, 0))],
    )

    # ── paned window ─────────────────────────────────────────────────────────
    s.configure("TPanedwindow", background=BORDER, sashpad=0)
    s.configure("Sash", sashthickness=4, gripcount=8)

    # ── scrollbar ─────────────────────────────────────────────────────────────
    s.configure("TScrollbar",
        background=BG_BTN,
        troughcolor=BG_INPUT,
        arrowcolor=FG_MUTED,
        bordercolor=BG,
        darkcolor=BG,
        lightcolor=BG_BTN,
        relief="flat",
    )
    s.map("TScrollbar",
        background=[("active", BG_ACTIVE)],
        arrowcolor=[("active", FG_DIM)],
    )

    # ── treeview ──────────────────────────────────────────────────────────────
    s.configure("Treeview",
        background=BG_INPUT,
        foreground=FG_DIM,
        fieldbackground=BG_INPUT,
        font=f["mono"],
        rowheight=22,
        bordercolor=BORDER,
        relief="flat",
    )
    s.map("Treeview",
        background=[("selected", SEL_BG)],
        foreground=[("selected", ACCENT)],
    )
    s.configure("Treeview.Heading",
        background=BG_BTN,
        foreground=FG_DIM,
        font=f["bold"],
        relief="flat",
        bordercolor=BORDER,
    )
    s.map("Treeview.Heading",
        background=[("active", BG_ACTIVE)],
        foreground=[("active", FG)],
    )

    # ── separator ─────────────────────────────────────────────────────────────
    s.configure("TSeparator", background=BORDER)
