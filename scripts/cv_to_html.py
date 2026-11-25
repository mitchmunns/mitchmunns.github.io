"""Turn the Word CV (mm_CV.docx) into HTML and put it in the CV section of
index.html, between the CV-START and CV-END markers.

Run it after replacing mm_CV.docx:
    python scripts/cv_to_html.py

Bold and italic are kept, links in the CV stay links, and dates go in a
right-hand column. The name, phone and address lines at the top of the CV are
left out (the page already shows the name and email).
Needs python-docx (pip install python-docx).
"""
import html
import re
import sys
from pathlib import Path

import docx
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parent.parent
DOCX = ROOT / "mm_CV.docx"
PAGE = ROOT / "index.html"
START, END = "<!-- CV-START -->", "<!-- CV-END -->"
HEADER_LINES = 3  # name/contact, department/address, interests


def run_html(run_el, text):
    rpr = run_el.find(qn("w:rPr"))
    bold = italic = False
    if rpr is not None:
        b, i = rpr.find(qn("w:b")), rpr.find(qn("w:i"))
        bold = b is not None and b.get(qn("w:val")) not in ("0", "false")
        italic = i is not None and i.get(qn("w:val")) not in ("0", "false")
    out = html.escape(text)
    if italic:
        out = f"<em>{out}</em>"
    if bold:
        out = f"<strong>{out}</strong>"
    return out, bold, italic


def para_html(p):
    """HTML for one paragraph, plus whether every piece of text is bold / italic."""
    parts, flags = [], []
    for child in p._p.iterchildren():
        if child.tag == qn("w:r"):
            text = "".join(t.text or "" for t in child.iter(qn("w:t")))
            if text:
                h, b, i = run_html(child, text)
                parts.append(h)
                flags.append((b, i, text))
        elif child.tag == qn("w:hyperlink"):
            rid = child.get(qn("r:id"))
            url = p.part.rels[rid].target_ref if rid in p.part.rels else None
            inner = []
            for r in child.iter(qn("w:r")):
                text = "".join(t.text or "" for t in r.iter(qn("w:t")))
                if text:
                    h, b, i = run_html(r, text)
                    inner.append(h)
                    flags.append((b, i, text))
            if inner:
                body = "".join(inner)
                linkable = url and re.sub(r"<[^>]+>", "", body).strip()
                parts.append(f'<a href="{html.escape(url)}" target="_blank" rel="noopener noreferrer">{body}</a>' if linkable else body)
    words = [f for f in flags if f[2].strip()]
    all_bold = bool(words) and all(f[0] for f in words)
    all_italic = bool(words) and all(f[1] for f in words)
    return "".join(parts).strip(), all_bold, all_italic


def is_heading(text, all_bold):
    return all_bold and len(text) < 60 and not re.search(r"\d", text)


def cell_lines(cell):
    lines = []
    for p in cell.paragraphs:
        h, _, _ = para_html(p)
        if h and h.strip():
            lines.append(h)
    return lines


def convert():
    d = docx.Document(str(DOCX))
    out = []
    seen_paras = 0
    for child in d.element.body.iterchildren():
        if child.tag == qn("w:p"):
            p = Paragraph(child, d)
            if not p.text.strip():
                continue
            seen_paras += 1
            if seen_paras <= HEADER_LINES:
                continue
            h, bold, italic = para_html(p)
            text = p.text.strip()
            if is_heading(text, bold):
                out.append(f'<h3 class="cv-head">{html.escape(text)}</h3>')
            elif italic and len(text) < 40:
                out.append(f'<h4 class="cv-sub">{html.escape(text)}</h4>')
            else:
                out.append(f'<p class="cv-entry">{h}</p>')
        elif child.tag == qn("w:tbl"):
            t = Table(child, d)
            for row in t.rows:
                cells = []
                for c in row.cells:  # merged cells repeat; keep each once
                    if not cells or c._tc is not cells[-1]._tc:
                        cells.append(c)
                left = cells[0]
                left_text = left.text.strip()
                rest = [x for x in cells[1:] if x.text.strip()]
                left_all_bold = all(para_html(p)[1] for p in left.paragraphs if p.text.strip())
                if not rest and is_heading(left_text, left_all_bold):
                    out.append(f'<h3 class="cv-head">{html.escape(left_text)}</h3>')
                    continue
                lines = cell_lines(left)
                if not lines:
                    continue
                date = html.escape(rest[0].text.strip()) if rest else ""
                body = "<br>".join(lines)
                out.append(f'<div class="cv-row"><div>{body}</div><div class="cv-date">{date}</div></div>')
    return "\n".join(out)


def main():
    fragment = convert()
    page = PAGE.read_text(encoding="utf-8")
    if START not in page or END not in page:
        sys.exit("CV markers not found in index.html")
    before, rest = page.split(START, 1)
    _, after = rest.split(END, 1)
    PAGE.write_text(before + START + "\n" + fragment + "\n" + END + after, encoding="utf-8")
    print(f"CV section updated ({fragment.count('cv-entry') + fragment.count('cv-row')} entries).")


if __name__ == "__main__":
    main()
