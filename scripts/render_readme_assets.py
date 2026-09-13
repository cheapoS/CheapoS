#!/usr/bin/env python3
"""Render the repository's Relay SVG templates using only the standard library."""

import argparse
from html import escape
import json
from pathlib import Path
from string import Template
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
PRESENTATION = ROOT / 'docs' / 'presentation'
ASSETS = ROOT / 'docs' / 'assets'


def render():
    tokens = json.loads((PRESENTATION / 'theme.json').read_text(encoding='utf-8'))['tokens']
    values = {key: escape(str(value), quote=True) for key, value in tokens.items()}
    icon = ET.parse(ROOT / 'dist' / 'brand-icon.svg').getroot()
    # Reuse the app's vector paths, but let the presentation theme own its colors.
    paths = ''.join(f'<path d="{escape(node.attrib["d"], quote=True)}"/>'
                    for node in icon.iter('{http://www.w3.org/2000/svg}path'))
    values['relay_icon'] = (f'<rect width="64" height="64" rx="16" fill="{values["mint"]}"/>'
                            f'<g fill="{values["background"]}">{paths}</g>')
    output = {}
    for template in sorted((PRESENTATION / 'templates').glob('*.svg')):
        content = Template(template.read_text(encoding='utf-8')).substitute(values)
        ET.fromstring(content)  # Fail before writing any file if a template is malformed.
        output[ASSETS / template.name] = content
    if not output:
        raise ValueError('No SVG templates found')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check generated assets without changing them')
    args = parser.parse_args()
    output = render()
    if args.check:
        stale = [str(path.relative_to(ROOT)) for path, content in output.items()
                 if not path.exists() or path.read_text(encoding='utf-8') != content]
        if stale:
            parser.exit(1, 'Regenerate assets with python3 scripts/render_readme_assets.py: '
                        + ', '.join(stale) + '\n')
        print(f'{len(output)} SVG assets match the theme and templates.')
    else:
        ASSETS.mkdir(parents=True, exist_ok=True)
        for path, content in output.items():
            path.write_text(content, encoding='utf-8')
            print(path.relative_to(ROOT))


if __name__ == '__main__':
    main()
