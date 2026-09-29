"""Consent-gated, bounded signed job manifests on the existing receipt chain."""
import copy
import hashlib
import json
import re
import uuid

FIELDS = ('job_id', 'started_at', 'authorized_at', 'ready_at', 'accepted_at', 'candidate_id',
          'acceptance_id', 'state', 'membership_complete', 'timing_complete', 'observation_complete',
          'active_ms', 'provider_wait_ms', 'operator_wait_ms', 'rescue_actions', 'approvals', 'unclassified_actions')


def sync_jobs(manager, lifetime):
    s = manager.state
    if not s.get('share_jobs') or not s.get('jobs_since'):
        return 0
    status = manager._call('status')
    if 'accepted_jobs_v1' not in (status.get('capabilities') or []):
        s['jobs_message'] = 'Finished-work sharing is waiting for Club server support. Evidence stays local.'
        return 0
    snapshot = s.get('job_upload')
    if not snapshot:
        acknowledged = set(s.get('attempts_sent', {})) | set(s.get('sent', {}))
        for job in lifetime.job_export():
            if not job.get('forward_observed') or job['started_at'] < s['jobs_since']:
                continue
            if any(r['request_id'] not in acknowledged for r in job['requests']):
                continue  # Exact request membership must link accepted facts first.
            header = {k: job[k] for k in FIELDS}
            members = []
            for r in sorted(job['requests'], key=lambda r: r['request_id']):
                member = {'event_id': str(uuid.uuid5(uuid.UUID(s['installation_id']), r['request_id'])),
                          'cost': None, 'currency': None, 'provenance': 'unknown'}
                if (isinstance(r.get('reported_cost_exact'), str) and re.fullmatch(r'(0|[1-9][0-9]{0,11})(\.[0-9]{1,30})?', r['reported_cost_exact'])
                        and re.fullmatch(r'[A-Z]{3}', str(r.get('reported_currency') or ''))):
                    member.update(cost=r['reported_cost_exact'], currency=r.get('reported_currency'), provenance='provider_reported')
                members.append(member)
            fingerprint = hashlib.sha256(json.dumps([header, members], sort_keys=True).encode()).hexdigest()
            if fingerprint in (s.get('jobs_sent', {}).get(job['job_id']), s.get('jobs_rejected', {}).get(job['job_id'])):
                continue
            revision = s.setdefault('job_revisions', {}).get(job['job_id'], 0) + 1
            pages = [members[n:n+20] for n in range(0, len(members), 20)] or [[]]
            header.update(version=1, revision=revision, request_count=len(members), page_count=len(pages))
            snapshot = dict(header=header, pages=pages, index=0, fingerprint=fingerprint)
            s['job_upload'] = snapshot
            s['job_revisions'][job['job_id']] = revision
            manager._save()
            break
    if not snapshot:
        return 0
    index = snapshot['index']
    manager._queue('sync', events=[], job_page=dict(header=copy.deepcopy(snapshot['header']),
                   index=index, members=snapshot['pages'][index]))
    manager._flush()
    return 1


def set_aside(manager, pending, error):
    """Drop a job page the Club definitely rejected so later usage can sync.

    Only a conflict on a page-only upload qualifies, and only while the Club
    cursor proves the page was not accepted. The job is retried if its evidence
    changes (a new fingerprint gets a new revision).
    """
    s = manager.state
    message = json.loads(pending['envelope']['payload'])
    snapshot = s.get('job_upload')
    if (error.code != 'conflict' or not message.get('job_page') or message.get('events') or message.get('request_attempts')
            or not snapshot or snapshot['header'] != message['job_page']['header']):
        return False
    remote = manager._call('status')
    if remote.get('sequence') != s['sequence'] or remote.get('previous_hash') != s['previous_hash']:
        return False
    s.setdefault('jobs_rejected', {})[snapshot['header']['job_id']] = snapshot['fingerprint']
    s.update(pending=None, job_upload=None,
             jobs_message='The Club rejected finished-work evidence for one job. Token usage keeps syncing; that job is retried only if its evidence changes.')
    manager._save()
    return True


def acknowledge(state, message):
    page = message.get('job_page')
    if not page:
        return
    snapshot = state.get('job_upload')
    if not snapshot or snapshot['header'] != page['header'] or snapshot['index'] != page['index']:
        raise ValueError('Finished-work acknowledgment does not match the retained manifest.')
    snapshot['index'] += 1
    if snapshot['index'] == len(snapshot['pages']):
        state.setdefault('jobs_sent', {})[snapshot['header']['job_id']] = snapshot['fingerprint']
        state['job_upload'] = None
    state['jobs_message'] = 'Finished-work evidence accepted by the Club.'
