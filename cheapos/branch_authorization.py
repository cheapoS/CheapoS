"""Ephemeral operator proposals and tightly bound, durable run contracts.

Only the trusted controller calls these helpers. HTTP callers supply a proposal
ID and decision, never the current contract or a grant to install.
"""
import copy
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import threading
import time

from . import branch_runs
from .project_permissions import config_identity, identity
from .test_profiles import executable_identity, unittest_selection


def digest(value):
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError('Authorization requires finite JSON values') from exc
    if len(encoded) > 1000000:
        raise ValueError('Authorization contract is too large')
    return hashlib.sha256(encoded.encode()).hexdigest()


def contract_builder(run, workspace_proposal, model_policy, check_scope):
    branch_runs.require_supported(run)
    plan = branch_runs.validate_plan(run['plan'])
    if run['limits'] != plan['limits']:
        raise ValueError('Plan and run limits disagree')
    value = {'run_id': run['id'], 'plan_revision': run['plan_revision'], 'plan': plan,
             'original_request': run['original_request'], 'inputs': run['inputs'],
             'project': run['project'], 'base_ref': run['base_ref'], 'base_sha': run['base_sha'],
             'target_ref': run['target_ref'], 'feature_ref': run['feature_ref'],
             'workspace_proposal': workspace_proposal, 'model_policy': model_policy,
             'limits': run['limits'], 'check_scope': check_scope,
             'scope': 'local_reviewed_feature_commits'}
    if 'settings_snapshot_digest' in run:
        value['settings_snapshot_digest']=run['settings_snapshot_digest']
    if 'integration_policy' in run:
        policy=run['integration_policy']
        if not isinstance(policy,dict) or set(policy)!={'keep_up_to_date','target_ref','target_tip'} or type(policy['keep_up_to_date']) is not bool or policy['target_ref']!=run['target_ref'] or not isinstance(policy['target_tip'],str) or not policy['target_tip']:
            raise ValueError('Integration preparation authority changed')
        value['integration_policy']=copy.deepcopy(policy)
    if not isinstance(model_policy, dict) or not model_policy:
        raise ValueError('Specify the authorized model policy')
    digest(value)
    return copy.deepcopy(value)


class ProposalRegistry:
    def __init__(self, clock=time.monotonic, ttl=300):
        if not isinstance(ttl, (int, float)) or isinstance(ttl, bool) or not 0 < ttl <= 3600:
            raise ValueError('Proposal lifetime must be 1–3600 seconds')
        self.clock, self.ttl = clock, ttl
        self.proposals = {}
        self.authorizations = {}
        self.lock = threading.RLock()

    def prepare(self, task_id, contract):
        fingerprint = digest(contract)
        with self.lock:
            stamp = self.clock()
            self.proposals = {k: v for k, v in self.proposals.items() if v['expires'] > stamp}
            if len(self.proposals) >= 1000:
                raise ValueError('Too many pending proposals; wait for expiry')
            token = secrets.token_urlsafe(32)
            self.proposals[token] = {'task_id': task_id, 'contract': copy.deepcopy(contract),
                                     'digest': fingerprint, 'expires': stamp + self.ttl, 'authorization_id': None}
            return {'proposal_id': token, 'expires_in': self.ttl, 'contract': copy.deepcopy(contract), 'digest': fingerprint}

    def authorize(self, task_id, proposal_id, approved, current_contract):
        if approved is not True:
            raise ValueError('Starting requires an explicit operator approval')
        if not isinstance(proposal_id, str):
            raise ValueError('A valid proposal ID is required')
        with self.lock:
            proposal = self.proposals.get(proposal_id)
            if not proposal or proposal['task_id'] != task_id or self.clock() >= proposal['expires']:
                raise ValueError('Proposal is missing, expired or belongs to another task')
            if not hmac.compare_digest(proposal['digest'], digest(current_contract)):
                raise ValueError('Proposal changed; inspect and authorize a fresh proposal')
            if proposal['authorization_id']:
                auth = self.authorizations[proposal['authorization_id']]
                if auth['status'] != 'active':
                    raise ValueError('Authorization was revoked; prepare a fresh proposal')
                return copy.deepcopy(auth)
            auth = {'id': secrets.token_hex(16), 'task_id': task_id, 'status': 'active',
                    'contract': copy.deepcopy(proposal['contract']), 'digest': proposal['digest'],
                    'scope': 'local_reviewed_feature_commits'}
            self.authorizations[auth['id']] = auth
            proposal['authorization_id'] = auth['id']
            return copy.deepcopy(auth)

    def revoke(self, authorization_id):
        with self.lock:
            if authorization_id not in self.authorizations:
                raise ValueError('Authorization not found')
            self.authorizations[authorization_id]['status'] = 'revoked'
            return copy.deepcopy(self.authorizations[authorization_id])

    def validate(self, authorization, current_contract):
        # Durable authority may be restored by the controller; ephemeral command
        # grants are deliberately not restored by this operation.
        with self.lock:
            known = self.authorizations.get(authorization.get('id'))
            if known is not None and known['status'] != 'active':
                raise ValueError('Run authorization was revoked')
            if authorization.get('status') != 'active' or authorization.get('scope') != 'local_reviewed_feature_commits':
                raise ValueError('Run authorization is not active')
            actual = digest(current_contract)
            if authorization.get('digest') != actual or digest(authorization.get('contract')) != actual:
                raise ValueError('Run scope changed; renewed authorization is required')
            return True


class CheckScopes:
    """Consent to exact commands or the existing narrowly supported profile.

Prepare against a controller-registered workspace before consent. Source Git is
not mutated. A projected scope must equal the materialized prepare() result.
"""
    def __init__(self, project_grants):
        self.project_grants = project_grants
        self.exact_grants = {}

    def prepare(self, task, argv):
        if not isinstance(argv, list) or not argv or any(not isinstance(a, str) or not a or '\0' in a for a in argv):
            raise ValueError('Supply an exact executable and argument list')
        self.project_grants.binding(task)
        profile = self.project_grants.proposal(task, argv)
        executable = executable_identity(argv[0], task['workspace'])
        if not executable:
            from .branch_pause import PauseError
            raise PauseError('missing_setup', diagnostic={'kind':'missing_executable','executable':argv[0]})
        stat = os.stat(executable)
        binding = {'source': identity(task['source']), 'workspace': identity(task['workspace']),
                   'executable': [executable, stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns],
                   'source_config': config_identity(task['source']), 'workspace_config': config_identity(task['workspace']),
                   'venv_config': config_identity(Path(executable).parent.parent),
                   'revision': self.project_grants.revisions.get(task['source'], 0)}
        return {'command': list(argv), 'directory': task['workspace'], 'profile': profile,
                'fingerprint': digest(binding)}

    def consent(self, task, scope, *, exact=False):
        current = self.prepare(task, scope['command'])
        if current != scope:
            raise ValueError('Runner, configuration or workspace changed; inspect fresh command scope')
        existing, _ = self.project_grants.authorize(task, scope['command'])
        if existing:
            return existing
        if scope['profile'] and not exact:
            return self.project_grants.approve(task, scope)['id']
        key = digest(scope)
        self.exact_grants[key] = copy.deepcopy(scope)
        return key

    def authorize(self, task, argv):
        granted, _ = self.project_grants.authorize(task, argv)
        if granted:
            return granted
        try:
            scope = self.prepare(task, argv)
        except (ValueError, OSError):
            return None
        key = digest(scope)
        if key in self.exact_grants:
            return key
        if "branch_run" in task and task["branch_run"].get("authorization_ref"):
            if scope.get("profile"):
                return self.consent(task, scope)
            for approved_scope in task["branch_run"].get("check_scope", []):
                if approved_scope.get("command") == list(argv) and approved_scope.get("directory") == task.get("workspace"):
                    if approved_scope == scope:
                        return self.consent(task, approved_scope)
        return None

    def approved_command(self, task, argv):
        """Reuse a captured check without expanding the operator's command grant."""
        selection = unittest_selection(argv)
        if selection is None:
            return list(argv)
        commands = [scope['command'] for scope in task.get('branch_run', {}).get('check_scope', [])]
        if argv in commands:
            return list(argv)
        for command in commands:
            if unittest_selection(command) == selection and self.authorize(task, command):
                # Revalidate live grants, including workspace, runner, configuration
                # and revocation. A saved plan alone never grants execution.
                return list(command)
        return list(argv)

    def revoke(self, grant_id):
        self.exact_grants.pop(grant_id, None)
