"""Journaled target-to-feature merge; target checkout and ref remain untouched."""
import copy
import tempfile
from pathlib import Path
from . import branch_workspace as work
from .branch_commits import repository_lock, _preserve_exclusions


def prepare(run):
    mapping = run['workspace_mapping']
    with repository_lock(mapping):
        old = run['expected_feature_tip']
        work.validate_owned(mapping, old)
        source, private = mapping['source'], mapping['workspace']
        work.inspect_source(private)
        if work.source_git(private, 'rev-parse', 'HEAD') != mapping['workspace_head']:
            raise ValueError('Task baseline changed; preserve and inspect saved edits before updating')
        if work.source_git(private, 'status', '--porcelain', '--untracked-files=all'):
            raise ValueError('Save the task’s uncommitted edits before updating its branch')
        target = work._tip(source, run['target_ref'])
        if not target: raise ValueError('The target branch no longer exists')
        try:
            work.source_git(source,'merge-base','--is-ancestor',target,old)
            current=True
        except ValueError:
            current=False
        if current: raise ValueError('Task branch already contains the target. Choose Recheck changes instead')
        tree, conflicts = merge_candidate(source, old, target)
        if conflicts:
            raise MergeConflict({'old_tip':old,'target_tip':target,'tree':tree,'files':conflicts})
        _preserve_exclusions(source, old, tree, mapping)
        patch = work.source_git(source, 'diff', '--binary', '--no-ext-diff', '--no-renames', old, tree, binary=True).decode('utf-8')
        with tempfile.TemporaryDirectory(prefix='cheapos-update-index-') as directory:
            index = Path(directory) / 'index'
            work.source_git(private, 'read-tree', 'HEAD', index=index)
            if patch: work.source_git(private, 'apply', '--cached', '--whitespace=nowarn', '-', input=patch, index=index)
            private_tree = work.source_git(private, 'write-tree', index=index)
        message = 'Update task branch with latest target'
        new = work.source_git(source, 'commit-tree', tree, '-p', old, '-p', target, input=message+'\n')
        private_new = work.source_git(private, '-c', 'user.name=cheapoS', '-c', 'user.email=local@cheapos.invalid',
                                      'commit-tree', private_tree, '-p', mapping['workspace_head'], input=message+'\n')
        return {'mapping':copy.deepcopy(mapping), 'old_tip':old, 'target_tip':target, 'target_ref':run['target_ref'],
                'new_tip':new, 'tree':tree, 'private_old':mapping['workspace_head'], 'private_new':private_new,
                'private_tree':private_tree, 'patch':patch, 'stage':'prepared'}


def finish(operation, persist):
    op = copy.deepcopy(operation)
    if op.get('approved') is not True or op.get('digest')!=receipt_digest(op):
        raise ValueError('Branch update approval receipt changed')
    mapping = op['mapping']
    source, private = mapping['source'], mapping['workspace']
    with repository_lock(mapping):
        actual = work._tip(source, mapping['feature_ref'])
        if actual not in {op['old_tip'], op['new_tip']}:
            raise ValueError('Task branch changed since update preparation; saved work is preserved')
        work.validate_owned(mapping, actual)
        # Finish only the already approved target commit, even if the target
        # advances again after interruption. Final review will detect that drift.
        target_now=work._tip(source, op['target_ref'])
        if not target_now: raise ValueError('Target branch no longer exists')
        head = work.source_git(private, 'rev-parse', 'HEAD')
        if head not in {op['private_old'], op['private_new']}:
            raise ValueError('Task baseline changed during update')
        if work.source_git(private, 'diff', '--name-only') or work.source_git(private, 'ls-files', '--others', '--exclude-standard'):
            raise ValueError('Task has new edits; finish or preserve them before retrying the saved update')
        tree = work.source_git(private, 'write-tree')
        old_tree = work.source_git(private, 'rev-parse', op['private_old']+'^{tree}')
        if tree not in {old_tree, op['private_tree']}:
            raise ValueError('Task index changed during update')
        op['stage'] = 'intent'; persist(copy.deepcopy(op))
        if tree != op['private_tree']:
            work.source_git(private, 'apply', '--index', '--whitespace=nowarn', '-', input=op['patch'])
        if head != op['private_new']:
            work.source_git(private, 'update-ref', 'HEAD', op['private_new'], op['private_old'])
        op['stage'] = 'private_updated'; persist(copy.deepcopy(op))
        if actual != op['new_tip']:
            transaction = ('start\noption no-deref\nverify '+mapping['ownership_ref']+' '+mapping['ownership_oid']+
                           '\nverify '+op['target_ref']+' '+target_now+
                           '\nupdate '+mapping['feature_ref']+' '+op['new_tip']+' '+op['old_tip']+'\nprepare\ncommit\n')
            work.source_git(source, 'update-ref', '--stdin', input=transaction)
        op['stage'] = 'completed'; persist(copy.deepcopy(op))
        return op


def receipt_digest(operation):
    from .branch_authorization import digest
    return digest({k:v for k,v in operation.items() if k not in {'stage','digest'}})


def advance_receipts(run, previous, private, updates):
    """Account for explicit integration commits without relaxing item receipts."""
    source=run['workspace_mapping']['source']
    while updates and updates[0]['old_tip']==previous:
        op=updates.pop(0)
        if op.get('stage')!='completed' or op.get('digest')!=receipt_digest(op) or op.get('approved') is not True:
            raise ValueError('Branch update approval receipt changed')
        if op['target_ref']!=run['target_ref'] or op['mapping']['source']!=source or op['mapping']['feature_ref']!=run['feature_ref'] or op['private_old']!=private:
            raise ValueError('Branch update does not match the saved task')
        if work.source_git(source,'rev-list','--parents','-n','1',op['new_tip']).split()!=[op['new_tip'],previous,op['target_tip']]:
            raise ValueError('Branch update ancestry changed')
        if work.source_git(source,'rev-parse',op['new_tip']+'^{tree}')!=op['tree']:
            raise ValueError('Branch update tree changed')
        private_repo=run['workspace_mapping']['workspace']
        if work.source_git(private_repo,'rev-list','--parents','-n','1',op['private_new']).split()!=[op['private_new'],private] or work.source_git(private_repo,'rev-parse',op['private_new']+'^{tree}')!=op['private_tree']:
            raise ValueError('Branch update private baseline changed')
        previous,private=op['new_tip'],op['private_new']
    return previous,private


class MergeConflict(ValueError):
    def __init__(self, context):
        self.context=context
        super().__init__('Conflicting changes found. Choose Resolve conflicts & recheck to have the agents combine both versions. Your branches are preserved.')


def merge_candidate(source, old, target):
    raw=work.source_git(source,'merge-tree','--write-tree','--name-only','-z',old,target,binary=True,allowed_returncodes=(0,1))
    parts=raw.split(b'\0')
    tree=parts[0].decode('ascii')
    if len(tree)!=40 or any(c not in '0123456789abcdef' for c in tree):
        raise ValueError('Git could not prepare a merge candidate')
    conflicts=[]
    for part in parts[1:]:
        if not part:break
        conflicts.append(part.decode('utf-8'))
    return tree,conflicts
