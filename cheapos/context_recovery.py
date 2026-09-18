"""Request projection and capacity failover; retained evidence is never deleted."""
import copy
import hashlib
import json
from .context_budget import payload_bytes
from .context_evidence import retain, preview


def project(task, messages, tools, role):
    projected = copy.deepcopy(messages)
    can_read = any(t['function']['name'] == 'read_context_evidence' for t in tools)
    reference = retain(task, messages, role + '_context')
    for message in projected:
        # Directions, review packets, coverage and tool envelopes remain exact.
        if message.get('role') == 'assistant' and not message.get('tool_calls'):
            if len(message.get('content') or '') > 2000:
                message['content'] = 'Earlier model analysis retained as historical evidence: ' + reference
        elif can_read and message.get('role') == 'tool' and len(message.get('content') or '') > 8000:
            try: value = json.loads(message['content'])
            except ValueError: value = {'content': message['content']}
            message['content'] = json.dumps(preview(task, value, limit=8000, head=2000, tail=1000))
    before, after = payload_bytes(messages, tools), payload_bytes(projected, tools)
    fingerprint = hashlib.sha256(json.dumps(projected, sort_keys=True).encode()).hexdigest()
    episode = task.setdefault('context_recovery', {}).setdefault(role, {'attempts': []})
    if after >= before or fingerprint in {a['digest'] for a in episode['attempts']}:
        return None
    episode['attempts'].append({'digest': fingerprint, 'reference': reference,
                                'before_bytes': before, 'after_bytes': after, 'strategy': 'evidence_projection'})
    return projected
