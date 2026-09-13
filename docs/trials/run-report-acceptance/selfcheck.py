"""No feature import: validate fixtures and demonstrate discriminating assertions."""
import hashlib
import json
from pathlib import Path
import sys
import time
import unittest
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from contract import task, has, private_absent, commit_present, commit_absent, unavailable, escaped, SHA, SECRET
from cheapos import branch_runs


class PackSelfCheck(unittest.TestCase):
    def test_compatible_fixture(self):
        value=task(); run=value['branch_run']; branch_runs.require_supported(run)
        self.assertEqual(branch_runs.validate_plan(run['plan']),run['plan'])
        receipt=run['items'][0]['commit_receipt']
        self.assertEqual(receipt['run_id'],run['id']); self.assertEqual(receipt['item_id'],run['items'][0]['id'])
        self.assertEqual(receipt['stage'],'completed'); self.assertEqual(receipt['new_tip'],run['expected_feature_tip'])
        self.assertNotIn('feature_branch',run)
    def test_negative_controls(self):
        # Minimal outputs from known-bad implementations: each must be rejected.
        controls=[(lambda s: has(s,'feature/report'),'feature_branch: None'),
                  (commit_present,'committed'), (commit_absent,SHA),
                  (private_absent,'prompt: '+SECRET),
                  (unavailable,'worker tokens: 0; reviewer tokens: 0; cost: 0'),
                  (escaped,'東京 |raw|\n# injected')]
        for assertion,bad in controls:
            with self.subTest(output=bad), self.assertRaises(AssertionError): assertion(bad)
        unavailable('Reviewer tokens: unavailable; cost: 0')
        escaped('東京 \\|raw\\| # injected'); private_absent('Safe title')


def digest():
    here=Path(__file__).parent
    names=('contract.py','example.py','test_formatter_acceptance.py','test_endpoint_acceptance.py','selfcheck.py','README.md')
    entries={name:hashlib.sha256((here/name).read_bytes()).hexdigest() for name in names}
    return {'algorithm':'sha256','files':entries,'pack_sha256':hashlib.sha256(json.dumps(entries,sort_keys=True,separators=(',',':')).encode()).hexdigest()}


if __name__=='__main__':
    if '--digest' in sys.argv:
        print(json.dumps(digest(),indent=2))
    elif '--verify' in sys.argv:
        saved=json.loads((Path(__file__).parent/'DIGEST.json').read_text())
        if saved != digest(): raise SystemExit('Acceptance pack changed: refuse qualification')
        print('Acceptance pack digest matches')
    else: unittest.main()
