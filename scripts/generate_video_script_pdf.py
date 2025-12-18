#!/usr/bin/env python3
"""Generate a simple PDF from docs/video_demo_script.md.

This is intentionally minimal (no Markdown styling) but produces a clean,
printable PDF you can upload/submit or keep as your recording checklist.

Usage:
  python scripts/generate_video_script_pdf.py \
    --input docs/video_demo_script.md \
    --output docs/video_demo_script.pdf
"""

from __future__ import annotations

import argparse
from pathlib import Path


def _wrap_line(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    out: list[str] = []
    cur = text
    while len(cur) > max_chars:
        cut = cur.rfind(" ", 0, max_chars)
        if cut <= 0:
            cut = max_chars
        out.append(cur[:cut].rstrip())
        cur = cur[cut:].lstrip()
    if cur:
        out.append(cur)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="docs/video_demo_script.md")
    parser.add_argument("--output", default="docs/video_demo_script.pdf")
    args = parser.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)

    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen.canvas import Canvas
    except Exception as e:
        raise SystemExit(
            "Missing dependency: reportlab. Install it with: pip install reportlab\n"
            f"Original error: {e}"
        )

    text = in_path.read_text(encoding="utf-8").splitlines()

    out_path.parent.mkdir(parents=True, exist_ok=True)

    page_w, page_h = letter
    margin = 54  # 0.75 in
    y = page_h - margin
    line_h = 12

    canvas = Canvas(str(out_path), pagesize=letter)
    canvas.setTitle(in_path.name)

    font = "Helvetica"
    mono = "Courier"

    in_code = False
    for raw in text:
        line = raw.rstrip("\n")

        # crude code block detection
        if line.strip().startswith("```"):
            in_code = not in_code
            continue

        canvas.setFont(mono if in_code else font, 10 if in_code else 11)
        max_chars = 100 if in_code else 110

        for wrapped in _wrap_line(line, max_chars=max_chars):
            if y <= margin:
                canvas.showPage()
                y = page_h - margin
                canvas.setFont(mono if in_code else font, 10 if in_code else 11)
            canvas.drawString(margin, y, wrapped)
            y -= line_h

    canvas.save()
    print(f"Wrote PDF: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
