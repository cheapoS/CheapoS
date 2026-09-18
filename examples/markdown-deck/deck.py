"""MarkdownDeck – zero‑dependency slide deck generator.

Provides:
* `MarkdownDeck` – parses a markdown string into slides, extracts presenter notes
  (HTML comments of the form ``<!-- note: … -->``) and renders a self‑contained
  HTML presentation.
* CLI with three sub‑commands:
  - ``build <src> <dst>`` – read a markdown file and write the HTML output.
  - ``serve <dir>`` – start a simple HTTP server (default port 8000).
  - ``export <src>`` – alias for ``build`` that writes ``<src>.html`` next to the
    source file.

Only the Python standard library is used.
"""

from __future__ import annotations

import argparse
import html
import os
import pathlib
import re
import sys
import http.server
import socketserver
from typing import List, Tuple

SLIDE_SEPARATOR = re.compile(r"^---\s*$", re.MULTILINE)
NOTE_PATTERN = re.compile(r"<!--\s*note:(.*?)-->", re.IGNORECASE)

# Very small markdown → HTML subset – sufficient for the tests.
def _markdown_to_html(md: str) -> str:
    lines = md.splitlines()
    out: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("# "):
            out.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            out.append(f"<h2>{html.escape(line[3:].strip())}</h2>")
        elif line.startswith("### "):
            out.append(f"<h3>{html.escape(line[4:].strip())}</h3>")
        elif line.lstrip().startswith("* "):
            # start a list
            out.append("<ul>")
            while i < len(lines) and lines[i].lstrip().startswith("* "):
                item = lines[i].lstrip()[2:].strip()
                out.append(f"  <li>{html.escape(item)}</li>")
                i += 1
            out.append("</ul>")
            continue
        elif line.startswith("```"):
            # fenced code block – collect until closing fence
            out.append("<pre><code>")
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                out.append(html.escape(lines[i]))
                i += 1
            out.append("</code></pre>")
        else:
            # plain paragraph – collapse multiple spaces
            stripped = line.strip()
            if stripped:
                out.append(f"<p>{html.escape(stripped)}</p>")
        i += 1
    return "\n".join(out)


class MarkdownDeck:
    """Core parser and renderer for a markdown slide deck.

    The public API is deliberately tiny so the unit‑tests can exercise the
    deterministic behaviour.
    """

    def __init__(self, markdown: str):
        self.raw = markdown.replace("\r\n", "\n")
        self.slides: List[str] = []          # HTML for each slide
        self.notes: List[str] = []           # Extracted presenter notes per slide
        self._parse()

    def _parse(self) -> None:
        # Split on lines that consist solely of three dashes.
        raw_slides = SLIDE_SEPARATOR.split(self.raw)
        for raw_slide in raw_slides:
            if not raw_slide.strip():
                continue
            # Extract note – keep only the first occurrence per slide.
            note_match = NOTE_PATTERN.search(raw_slide)
            note = note_match.group(1).strip() if note_match else ""
            self.notes.append(note)
            # Remove the note comment before markdown conversion.
            slide_without_note = NOTE_PATTERN.sub("", raw_slide)
            html_slide = _markdown_to_html(slide_without_note)
            self.slides.append(html_slide)

    # ---------------------------------------------------------------------
    # Rendering helpers
    # ---------------------------------------------------------------------
    _HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Markdown Deck</title>
<style>{css}</style>
</head>
<body>
<div id="deck">
{slides}
</div>
<script>{js}</script>
</body>
</html>"""

    _CSS = """
body {{ margin:0; background:#fff; color:#000; font-family:system-ui, sans-serif; }}
.slide {{ display:none; padding:2rem; min-height:100vh; box-sizing:border-box; }}
.slide.active {{ display:block; }}
.note {{ font-size:0.8rem; color:#555; margin-top:1rem; }}
[data-theme='dark'] {{ background:#111; color:#eee; }}
"""

    _JS = """
let idx = 0;
const slides = document.querySelectorAll('.slide');
function show(i) {{
  slides.forEach(s=>s.classList.remove('active'));
  slides[i].classList.add('active');
}}
function next() {{ if (idx < slides.length-1) {{ idx++; show(idx); }} }}
function prev() {{ if (idx > 0) {{ idx--; show(idx); }} }}
function goStart() {{ idx = 0; show(idx); }}
function goEnd() {{ idx = slides.length-1; show(idx); }}
function toggleTheme() {{
  const cur = document.documentElement.getAttribute('data-theme')||'light';
  document.documentElement.setAttribute('data-theme', cur==='light'?'dark':'light');
}}
function toggleFull() {{
  if (!document.fullscreenElement) { document.documentElement.requestFullscreen(); }
  else { document.exitFullscreen(); }
}}
document.addEventListener('keydown', e=>{{
  switch(e.key){{
    case 'ArrowRight': case ' ': next(); break;
    case 'ArrowLeft': prev(); break;
    case 'Home': goStart(); break;
    case 'End': goEnd(); break;
    case 'f': case 'F': toggleFull(); break;
    case 't': case 'T': toggleTheme(); break;
  }}
}});
show(0);
"""

    def render(self) -> str:
        """Return a deterministic, self‑contained HTML string.

        Each slide is wrapped in ``<section class="slide">`` and, if a note was
        extracted, a ``<div class="note">`` element is appended.
        """
        slide_html_parts: List[str] = []
        for html_body, note in zip(self.slides, self.notes):
            parts = ["<section class='slide'>", html_body]
            if note:
                parts.append(f"<div class='note'>{html.escape(note)}</div>")
            parts.append("</section>")
            slide_html_parts.append("\n".join(parts))
        slides_combined = "\n".join(slide_html_parts)
        return self._HTML_TEMPLATE.format(css=self._CSS, js=self._JS, slides=slides_combined)

    # ---------------------------------------------------------------------
    # Static convenience helpers used by the CLI
    # ---------------------------------------------------------------------
    @staticmethod
    def build(src_path: str, dst_path: str) -> None:
        """Read *src_path* (markdown) and write the generated HTML to *dst_path*.
        """
        md = pathlib.Path(src_path).read_text(encoding="utf-8")
        deck = MarkdownDeck(md)
        pathlib.Path(dst_path).write_text(deck.render(), encoding="utf-8")

    @staticmethod
    def serve(directory: str, port: int = 8000) -> None:
        """Serve *directory* over HTTP – useful for quick local preview.
        """
        os.chdir(directory)
        handler = http.server.SimpleHTTPRequestHandler
        with socketserver.TCPServer(("", port), handler) as httpd:
            print(f"Serving {directory} at http://localhost:{port}")
            httpd.serve_forever()


def _cli() -> None:
    parser = argparse.ArgumentParser(prog="deck", description="MarkdownDeck – zero‑dependency slide deck generator")
    sub = parser.add_subparsers(dest="cmd", required=True)

    build = sub.add_parser("build", help="Compile markdown to a single‑file HTML deck")
    build.add_argument("src", help="Path to the markdown source file")
    build.add_argument("dst", nargs='?', default='index.html', help="Optional path for the generated HTML file (default: index.html)")

    serve = sub.add_parser("serve", help="Serve a directory containing generated decks")
    serve.add_argument("dir", nargs="?", default=".", help="Directory to serve (default: current)")
    serve.add_argument("--port", type=int, default=8000, help="Port number (default: 8000)")

    export = sub.add_parser("export", help="Convenient alias for build – writes <src>.html next to source")
    export.add_argument("src", help="Path to the markdown source file")
    export.add_argument("dst", nargs='?', default=None, help="Optional output path for the generated HTML file")

    args = parser.parse_args()
    if args.cmd == "build":
        MarkdownDeck.build(args.src, args.dst)
    elif args.cmd == "serve":
        path = pathlib.Path(args.dir)
        dir_path = path.parent if path.is_file() else path
        MarkdownDeck.serve(str(dir_path), args.port)
    elif args.cmd == "export":
        src_path = pathlib.Path(args.src)
        dst_path = pathlib.Path(args.dst) if hasattr(args, 'dst') and args.dst else src_path.with_suffix('.html')
        MarkdownDeck.build(str(src_path), str(dst_path))
    else:
        parser.error("Unknown command")

if __name__ == "__main__":
    _cli()