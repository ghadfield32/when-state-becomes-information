"""Render abstract.pdf from abstract.txt.

Presentation only: this never recomputes a result. It reads the frozen abstract
text, so the PDF cannot drift from the submitted words.

Wrapping is measured against the real renderer rather than guessed from a
character count. A fixed character width silently overflowed the page margin in
the first version of this file.

Uses matplotlib, which is ALREADY in this repository's locked environment.
Adding a PDF library would change the pinned `uv.lock` hash recorded in
REPRODUCTION_RECEIPT.json, so the scientific environment is left intact.

    python make_abstract_pdf.py
"""
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

HERE = Path(__file__).resolve().parent
SRC = HERE / "abstract.txt"
OUT = HERE / "abstract.pdf"

TITLE = ("When State Becomes Information: Release-Conditioned "
         "Basketball Forecasting")
AUTHOR = "Geoffrey Hadfield"
AFFIL = "World Model Sports LLC"
EMAIL = "geoff@worldmodelsports.com"
REPO = "https://github.com/ghadfield32/ssac27-release-conditioned-forecasting"
SCI_TAG = "e1-2026-10-01"
SECTIONS = ("Introduction.", "Methods.", "Results.", "Conclusion.")

LEFT, RIGHT = 0.085, 0.915
TOP = 0.946
ROW_H_IN = 0.165


def main():
    if not SRC.exists():
        sys.exit(f"missing {SRC.name}")
    lines = SRC.read_text(encoding="utf-8").splitlines()

    body = [l.strip() for l in lines if l.strip().startswith(SECTIONS)]
    rows = [l for l in lines if l.strip().startswith("|")]
    table = []
    for r in rows:
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        if all(set(c) <= set(":-") and c for c in cells):
            continue
        table.append(cells)
    note = None
    for l in lines:
        s = l.strip()
        if s and not s.startswith(SECTIONS) and not s.startswith("|") \
                and not s.startswith("Table 1") and s != TITLE:
            note = s

    fig = plt.figure(figsize=(8.5, 11), dpi=100)
    canvas = fig.add_axes([0, 0, 1, 1]); canvas.axis("off")
    renderer = fig.canvas.get_renderer()
    fig_h, fig_w = fig.get_figheight(), fig.get_figwidth()
    max_px = (RIGHT - LEFT) * fig_w * fig.dpi

    def wrap(text, fontsize, style):
        words, out, cur = text.split(), [], ""
        for w in words:
            cand = f"{cur} {w}".strip()
            probe = canvas.text(0, 0, cand, fontsize=fontsize, style=style)
            too_wide = probe.get_window_extent(renderer=renderer).width > max_px
            probe.remove()
            if too_wide and cur:
                out.append(cur); cur = w
            else:
                cur = cand
        if cur:
            out.append(cur)
        return out

    y_in = fig_h * (1 - TOP)

    def block(text, fontsize, weight="normal", leading=1.42, gap_in=0.075,
              style="normal", color="black"):
        nonlocal y_in
        line_h = fontsize * leading / 72.0
        for ln in wrap(text, fontsize, style):
            fig.text(LEFT, 1 - y_in / fig_h, ln, fontsize=fontsize,
                     weight=weight, style=style, ha="left", va="baseline",
                     color=color, family="serif")
            y_in += line_h
        y_in += gap_in

    block(TITLE, 14.0, "bold", leading=1.26, gap_in=0.06)
    block(f"{AUTHOR}  \u00b7  {AFFIL}  \u00b7  {EMAIL}", 9.4, color="#333333",
          leading=1.3, gap_in=0.17)
    for para in body:
        label, _, rest = para.partition(" ")
        block(f"{label} {rest}", 10.0, gap_in=0.075)
    if note:
        block(note, 8.7, color="#444444", leading=1.35, gap_in=0.10)

    if table:
        y_in += 0.03
        n = len(table)
        h_in = n * ROW_H_IN
        ax_t = fig.add_axes([LEFT, (fig_h - y_in - h_in) / fig_h,
                             RIGHT - LEFT, h_in / fig_h])
        ax_t.axis("off")
        # Explicit column widths: the first column holds long timing labels and
        # is truncated if the columns are left to auto-size.
        ncols = len(table[0])
        if ncols == 6:
            col_widths = [0.33, 0.135, 0.185, 0.115, 0.115, 0.12]
        else:
            col_widths = [1.0 / ncols] * ncols
        t = ax_t.table(cellText=table[1:], colLabels=table[0], loc="center",
                       cellLoc="right", colWidths=col_widths)
        t.auto_set_font_size(False)
        t.set_fontsize(9.0)
        for (r, c), cell in t.get_celld().items():
            cell.set_linewidth(0.0)
            cell.set_edgecolor("#333333")
            if r == 0:
                cell.set_text_props(weight="bold")
                cell.set_linewidth(0.6); cell.visible_edges = "B"
            elif r == n - 1:
                cell.set_linewidth(0.6); cell.visible_edges = "T"
            if c == 0:
                cell.set_text_props(ha="left"); cell._loc = "left"
        y_in += h_in + 0.12

    fig.text(LEFT, 1 - (y_in + 0.05) / fig_h,
             f"Supporting repository: {REPO}   |   scientific release: {SCI_TAG}",
             fontsize=8.0, ha="left", va="baseline", color="#1a4d8f")

    # Deterministic output: omit timestamps and producer strings so the same
    # abstract.txt yields identical bytes.
    meta = {"CreationDate": None, "ModDate": None,
            "Producer": None, "Creator": None}
    with PdfPages(OUT, metadata=meta) as pdf:
        pdf.savefig(fig)
    plt.close(fig)

    used_in = y_in + 0.05
    if used_in > fig_h:
        print(f"WARNING: content is {used_in:.2f}in but the page is {fig_h:.2f}in",
              file=sys.stderr)
    print(f"wrote {OUT.name} ({OUT.stat().st_size} bytes) from {SRC.name}; "
          f"content height {used_in:.2f}in of {fig_h:.2f}in")


if __name__ == "__main__":
    main()
