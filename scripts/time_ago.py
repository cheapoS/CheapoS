#!/usr/bin/env python3
"""Format ISO timestamps or unix epoch seconds into human-readable relative strings."""

import argparse
import json
import sys
from datetime import datetime, timezone


def parse_timestamp(value):
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    raise ValueError(f"Cannot parse timestamp: {value}")


def time_ago(target, now=None):
    if now is None:
        now = datetime.now(tz=timezone.utc)
    if target is None:
        return "just now"
    if isinstance(target, str):
        target = parse_timestamp(target)
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    diff = now - target
    total_seconds = diff.total_seconds()

    if total_seconds < 0:
        return "just now"

    minutes = total_seconds / 60
    hours = total_seconds / 3600

    if total_seconds < 60:
        return "just now"
    if minutes < 60:
        n = int(minutes)
        return f"{n} minute{'s' if n != 1 else ''} ago"
    if hours < 24:
        n = int(hours)
        return f"{n} hour{'s' if n != 1 else ''} ago"
    n = int(total_seconds // 86400)
    if n >= 7:
        return target.strftime("%Y-%m-%d")
    if n == 1:
        return "yesterday"
    return f"{n} day{'s' if n != 1 else ''} ago"


def main():
    parser = argparse.ArgumentParser(description="Format timestamps as relative time.")
    parser.add_argument("timestamps", nargs="*", help="ISO timestamps or epoch seconds")
    parser.add_argument("--now", help="Reference timestamp for testing")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    offending = None
    try:
        now = None
        if args.now:
            offending = args.now
            now = parse_timestamp(args.now)
        parsed_timestamps = []
        for ts in args.timestamps:
            offending = ts
            parsed_timestamps.append(parse_timestamp(ts))
    except ValueError:
        print(f"Error: cannot parse timestamp: {offending}", file=sys.stderr)
        sys.exit(1)

    if not parsed_timestamps:
        result = time_ago(datetime.now(tz=timezone.utc), now=now)
    elif len(parsed_timestamps) == 1:
        result = time_ago(parsed_timestamps[0], now=now)
    else:
        result = [time_ago(ts, now=now) for ts in parsed_timestamps]

    if args.json:
        print(json.dumps(result))
    else:
        print(result)


if __name__ == "__main__":
    main()