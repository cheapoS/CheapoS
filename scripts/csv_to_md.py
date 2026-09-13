#!/usr/bin/env python3
"""Convert CSV to an aligned GitHub-flavored Markdown table."""

import argparse
import csv
import sys


def read_rows(path, delimiter):
    """Read CSV rows from a file path or stdin."""
    if path and path != '-':
        with open(path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=delimiter)
            return list(reader)
    reader = csv.reader(sys.stdin, delimiter=delimiter)
    return list(reader)


def column_widths(rows):
    """Compute the maximum display width for each column."""
    widths = []
    for row in rows:
        for i, cell in enumerate(row):
            if i >= len(widths):
                widths.append(0)
            widths[i] = max(widths[i], len(cell))
    return widths


def format_row(cells, widths):
    """Format a single row with left-aligned, padded columns."""
    padded = [cell.ljust(width) for cell, width in zip(cells, widths)]
    return '| ' + ' | '.join(padded) + ' |'


def format_separator(widths):
    """Format the separator row (e.g. | --- | --- |)."""
    parts = ['---' for _ in widths]
    return '| ' + ' | '.join(parts) + ' |'


def to_markdown(rows, has_header=True):
    """Convert a list of CSV rows into a markdown table string."""
    if not rows:
        return ''

    widths = column_widths(rows)
    lines = []

    if has_header:
        lines.append(format_row(rows[0], widths))
        lines.append(format_separator(widths))
        data_rows = rows[1:]
    else:
        data_rows = rows

    for row in data_rows:
        lines.append(format_row(row, widths))

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Convert CSV to Markdown table.')
    parser.add_argument('path', nargs='?', help='CSV file path (default: stdin)')
    parser.add_argument('--delimiter', default=',', help='Field delimiter (default: comma)')
    parser.add_argument('--no-header', action='store_true', help='Treat all rows as data (no header/separator)')
    args = parser.parse_args()

    rows = read_rows(args.path, args.delimiter)
    markdown = to_markdown(rows, has_header=not args.no_header)
    print(markdown)


if __name__ == '__main__':
    main()