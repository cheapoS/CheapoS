"""Read-only first-use diagnostics. No inference, installs, or process ownership changes."""
import copy
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from .omniroute import find_executable
from .startup import local_candidates

BASELINE = '3.8.49'
VERSION = re.compile(r'^v?(\d+\.\d+\.\d+)(?:[-+][\w.-]+)?$')


def prerequisites():
    executable = find_executable()
    cli_version = None
    if executable:
        # npm installs put the package manifest above the resolved bin entry.
        # Read it instead of launching a gateway just to inspect its version.
        for directory in list(Path(executable).resolve().parents)[:4]:
            try:
                data = json.loads((directory / 'package.json').read_text())
                if data.get('name') == 'omniroute' and VERSION.fullmatch(str(data.get('version', ''))):
                    cli_version = data['version']
                    break
            except (OSError, ValueError, AttributeError):
                pass
    node = shutil.which('node')
    node_version = None
    if node:
        try:
            result = subprocess.run([node, '--version'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2,
                                    env={key:value for key,value in os.environ.items() if key in {'PATH','SystemRoot','WINDIR','LANG'}})
            match = VERSION.fullmatch(result.stdout.decode('utf-8', 'replace').strip())
            if result.returncode == 0 and match: node_version = match.group(1)
        except (OSError, subprocess.TimeoutExpired):
            pass
    return {'node': {'installed':bool(node),'version':node_version},
            'omniroute': {'installed':bool(executable),'version':cli_version,
                          'compatibility':'validated_baseline' if cli_version == BASELINE else 'unverified',
                          'validated_baseline':BASELINE}}


def describe(gateway, prerequisites, locals_, execution, startup, direct=False):
    """Versioned response built only from metadata, never a greeting's claims."""
    installed = prerequisites['omniroute']['installed']
    status = gateway['status']
    code = gateway.get('diagnostic_code')
    if status in {'checking','starting'} or gateway.get('busy'):
        state, action = 'starting', 'wait'
    elif status == 'auth_required' or code == 'client_key_rejected':
        state, action = 'client_key_rejected', 'enter_client_key'
    elif code == 'unidentified_service':
        state, action = 'foreign_service', 'choose_gateway_endpoint'
    elif status == 'ready':
        state, action = ('gateway_ready','open_project') if gateway.get('free_count',0) else ('no_eligible_model','configure_provider')
    elif status == 'unavailable':
        state, action = 'offline', 'inspect_gateway'
    elif gateway.get('settings', {}).get('gateway_type', 'omniroute') != 'omniroute':
        state, action = 'offline', 'inspect_gateway'
    elif not installed:
        state, action = 'gateway_absent', 'install_gateway' if prerequisites['node']['installed'] else 'install_node'
    elif status in {'offline','not_installed','unchecked','stopped'} and not gateway.get('owned'):
        state, action = 'gateway_stopped', 'start_gateway'
    else:
        state, action = 'offline', 'inspect_gateway'
    names = [candidate['config']['model'] for candidate in locals_]
    selected = execution.get('local_model')
    required = [execution.get(key) for key in ('local_model','local_reviewer','local_planner')] if execution.get('mode') == 'local' else [selected]
    local_ready = bool(names and all(not model or model in names for model in required))
    if execution.get('mode') == 'local':
        state, action = ('local_only_ready','open_project') if local_ready else ('local_unavailable','check_local_models')
    greeting = startup.get('status') == 'ready' and bool(startup.get('verified_at'))
    return {'schema_version':1, 'status':state, 'next_step':action,
            'prerequisites':prerequisites,
            'gateway':{'identified':status == 'ready', 'status':status, 'owned':bool(gateway.get('owned')), 'pid':gateway.get('pid'),
                       'dashboard_url':gateway.get('dashboard_url') if status == 'ready' else None,
                       'client_key_configured':bool(gateway.get('key_configured')), 'diagnostic_code':code,
                       'key_storage':{key:gateway.get('key_storage', {}).get(key) for key in ('available','backend','saved','source','error')},
                       'model_count':gateway.get('model_count',0), 'eligible_free_count':gateway.get('free_count',0),
                       'service_version':None, 'optional_apis':{'setup':False,'provider_enrollment':False}},
            'paths':{'local':{'status':'ready' if local_ready else 'unavailable','models':names,'selected':selected or None},
                     'direct':{'configured':bool(direct),'status':'configured_unverified' if direct else 'not_configured'}},
            'levels':{'catalog':status == 'ready','local_metadata':local_ready,'greeting':greeting,
                      'usage_reporting':greeting and bool(startup.get('usage')),'coding':False,'checks':False,'review':False}}


class ReadinessManager:
    def __init__(self, engine):
        self.engine = engine
        self.lock = threading.RLock()
        self.thread = None
        self.closed = False
        self.checked_at = 0
        self.local_checked_at = 0
        self.local_selection = None
        self.locals = []
        self.state = {'schema_version':1,'status':'checking','next_step':'wait'}

    def inspect(self):
        engine = self.engine
        prerequisites_ = prerequisites()
        gateway = engine.gateway.snapshot()
        if not gateway.get('busy'):
            refreshed = engine.gateway.refresh(start=False)
            if gateway['status'] == 'unchecked': gateway = refreshed
        execution = engine.preferences()['execution']
        selection = (execution.get('local_model'), execution.get('local_reviewer'), execution.get('local_planner'))
        if time.monotonic()-self.local_checked_at >= 30 or not self.local_checked_at or selection != self.local_selection:
            self.locals = local_candidates(engine.config.get('worker'), preferred=selection)
            self.local_checked_at = time.monotonic()
            self.local_selection = selection
        direct = all(engine.config.get(role) and engine.config[role].get('gateway') != 'omniroute' for role in ('worker','reviewer'))
        result = describe(gateway, prerequisites_, self.locals, execution, engine.startup.snapshot(), direct)
        planner = engine.config.get('planner') or engine.config.get('reviewer')
        if execution.get('mode') == 'local':
            model = execution.get('local_planner') or execution.get('local_reviewer') or execution.get('local_model')
            status = 'metadata_ready' if model in result['paths']['local']['models'] else 'model_missing'
        else:
            model = (planner or {}).get('model')
            status = 'not_configured' if not model else 'configured_unverified'
            if planner and planner.get('gateway') == 'omniroute':
                if gateway.get('status') == 'auth_required': status = 'client_key_needed'
                elif gateway.get('status') != 'ready': status = 'gateway_unavailable'
                else:
                    models = engine.gateway.catalog(fresh=False).get('models', [])
                    status = 'metadata_ready' if any(m.get('id') == model and m.get('tool_calling') is True for m in models) else 'model_missing'
            elif planner and str(planner.get('base_url', '')).startswith('https://') and not engine.provider_key('planner' if engine.config.get('planner') else 'reviewer', planner):
                status = 'client_key_needed'
        result['paths']['planner'] = {'model': model, 'status': status, 'fallback': not bool(execution.get('local_planner') if execution.get('mode') == 'local' else engine.config.get('planner'))}
        return result

    def _refresh(self):
        try:
            result = self.inspect()
        except Exception:
            # Never turn a probe failure into task-history failure or leak raw configuration.
            result = {'schema_version':1,'status':'offline','next_step':'recheck','diagnostic_code':'readiness_probe_failed'}
        with self.lock:
            if not self.closed:
                self.state = result
                self.checked_at = time.monotonic()

    def snapshot(self, refresh=False):
        with self.lock:
            busy = bool(self.thread and self.thread.is_alive())
            if refresh and not busy:
                self.checked_at = 0
                self.local_checked_at = 0
            interval = 2 if refresh or self.state['status'] in {'checking','starting'} else 15
            if not self.closed and not busy and (not self.checked_at or time.monotonic()-self.checked_at >= interval):
                self.thread = threading.Thread(target=self._refresh, daemon=True)
                self.thread.start()
                busy = True
            return {**copy.deepcopy(self.state),'checking':busy}

    def shutdown(self):
        self.closed = True
        if self.thread: self.thread.join(1)
