import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from cheapos import commits, reconciliation
from cheapos.verification import evidence_identity
from cheapos.engine import Engine, Runtime, needs_patch_review
from cheapos.workspace import Workspace, git


class CommitCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = Engine(Path(self.temp.name) / 'state')
        self.task = self.engine.create_demo()
        self.source = Path(self.task['source'])
        git(self.source, 'config', 'user.name', 'Test Operator')
        git(self.source, 'config', 'user.email', 'operator@example.invalid')
        self.workspace = Workspace(self.task['workspace'])
        self.workspace.write_file('approved.txt', 'approved content\n')
        self.review()
        self.head = git(self.source, 'rev-parse', 'HEAD').strip()

    def tearDown(self):
        self.engine.shutdown()
        self.temp.cleanup()

    def review(self, status='approved'):
        self.engine.refresh_changes(self.task)
        self.task['status'] = status
        generation = self.task.get('workspace_generation', 0)
        self.task['checks'].append({'passed': True, 'digest': hashlib.sha256(self.task['patch'].encode()).hexdigest(), 'generation': generation, 'verification_identity': evidence_identity(self.task)})
        self.task['checkpoints'].append({'decision': 'APPROVE', 'diff': self.task['patch'], 'worker_summary': 'Add approved example', 'generation': generation, 'verification_identity': evidence_identity(self.task)})
        self.engine.store.save(self.task)

    def preview(self):
        return self.engine.prepare_commit(self.task['id'])

    def approve(self, preview, **extra):
        return self.engine.apply_commit(self.task['id'], {'approved': True, 'approval_id': preview['approval_id'], 'message': preview['message'], **extra})

    def reconcile(self):
        return self.engine.reconcile_project(self.task['id'], {'patch_digest': hashlib.sha256(self.task['patch'].encode()).hexdigest()})

    def source_change(self, name, content):
        (self.source / name).write_text(content)
        git(self.source, 'add', '--', name)
        git(self.source, 'commit', '-qm', 'Separate project changes')
