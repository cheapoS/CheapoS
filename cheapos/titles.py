"""Deterministic presentation-only task names; execution history stays unchanged."""
import re

# Exact greeting-only matches, with optional trailing greeting punctuation.
GREETINGS = {'hi', 'hello', 'hey', 'hi gemma', 'hello gemma', 'hey gemma'}


def automatic_title(task):
    for request in task.get('requests') or [task.get('prompt', task.get('title', ''))]:
        if not isinstance(request, str):
            continue
        normalized = ' '.join(request.split())
        if not normalized or normalized.casefold().rstrip('!.?') in GREETINGS:
            continue
        line = next((line.strip() for line in request.splitlines() if line.strip()), normalized)
        title = re.split(r'(?<=[.!?])\s+', ' '.join(line.split()), maxsplit=1)[0]
        if len(title) > 72:
            cut = title[:71]
            title = (cut.rsplit(' ', 1)[0] if ' ' in cut else cut) + '…'
        return title
    return 'New chat'
