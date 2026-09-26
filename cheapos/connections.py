"""Saved gateway adapters. Editing selection is independent of running placement."""
import json
import re
import threading
import uuid
from pathlib import Path

from . import access_policy, route_health
from .model_pool import FreeModelPool
from .omniroute import OmniRouteManager
from .providers import ProviderError
from .storage import write_json


class ConnectionPool(FreeModelPool):
    """Share only explicit upstream quota groups, never gateway transport failures."""
    def __init__(self, root, registry):
        super().__init__(root)
        self.registry = registry

    def group(self, endpoint, model, revision):
        prefix = model.split('/')[0]
        for manager in tuple(self.registry.managers.values()):
            if manager.matches(endpoint) and manager.settings.get('connection_revision') == revision:
                return manager.settings.get('quota_groups', {}).get(prefix)
        return None

    def observation(self, endpoint, model, connection_revision=None):
        result = super().observation(endpoint, model, connection_revision)
        group = self.group(endpoint, model, connection_revision)
        if group:
            shared = super().observation('quota-group:' + group, model)
            if shared.get('cooling_down') and shared.get('retry_at',0) >= result.get('retry_at',0):
                result.update(shared)
                result['shared_quota_group'] = group
        return result

    def record(self, endpoint, model, role, **kwargs):
        super().record(endpoint, model, role, **kwargs)
        error = kwargs.get('error')
        group = self.group(endpoint, model, kwargs.get('connection_revision'))
        failure = route_health.classify(error) if error else {}
        if group and failure.get('category') == 'rate_limit_quota' and failure.get('scope') in {'provider','account'}:
            shared = ProviderError('This upstream account is cooling down across its configured gateways.',
                                   code='gateway_cooldown', scope='account', retry_after=getattr(error,'retry_after',None))
            super().record('quota-group:' + group, model, role, error=shared)


class Connections:
    def __init__(self, root, default):
        self.root = Path(root)
        self.path = self.root / 'connections.json'
        self.lock = threading.RLock()
        self.managers = {'default': default}
        try:
            saved = json.loads(self.path.read_text())
        except (OSError, ValueError):
            saved = {}
        if not isinstance(saved,dict): saved={}
        identities=saved.get('ids',[])
        if not isinstance(identities,list): identities=[]
        for identity in identities[:20]:
            if identity != 'default' and isinstance(identity,str) and re.fullmatch('[a-f0-9]{32}', identity):
                self.managers[identity] = OmniRouteManager(self.root / 'connections' / identity, use_environment=False)
        self.selected_id = saved.get('selected', 'default')
        if not isinstance(self.selected_id,str) or self.selected_id not in self.managers: self.selected_id = 'default'
        self.pool = ConnectionPool(root, self)
        for identity, manager in self.managers.items():
            manager.connection_id = identity
            manager.pool = self.pool

    @property
    def selected(self):
        return self.managers[self.selected_id]

    def save(self):
        write_json(self.path, {'ids':list(self.managers), 'selected':self.selected_id})

    def snapshot(self):
        result = self.selected.snapshot()
        result['selected_connection'] = self.selected_id
        result['connections'] = [{'id':identity, 'name':m.settings['name'],
                                  'enabled':m.settings['enabled'], 'gateway_type':m.settings['gateway_type'],
                                  'automatic':m.settings.get('automatic', True),
                                  'models':[{'id':model['id'], 'label':model.get('name',model['id'])} for model in m.models],
                                  'status':m.state} for identity,m in tuple(self.managers.items())]
        return result

    def select(self, identity):
        with self.lock:
            if identity not in self.managers: raise ValueError('Choose a saved connection')
            previous = self.selected_id
            self.selected_id = identity
            try: self.save()
            except OSError:
                self.selected_id = previous
                raise
        return self.selected

    def add(self, values):
        with self.lock:
            if len(self.managers) >= 20: raise ValueError('Up to 20 gateway connections are supported')
            identity = uuid.uuid4().hex
            manager = OmniRouteManager(self.root / 'connections' / identity, use_environment=False)
            manager.configure({'automatic': values.get('gateway_type') != 'direct', **values, 'auto_start':False})
            manager.connection_id = identity
            manager.pool = self.pool
            self.managers[identity] = manager
            try: self.save()
            except OSError:
                self.managers.pop(identity)
                raise
            return identity

    def resolve(self, config, fallback):
        identity = config.get('connection_id')
        if identity is None:
            # Legacy tasks remain bound to their original endpoint, not the UI dropdown.
            if fallback.matches(config.get('base_url','')): return fallback
            matches = [m for m in self.managers.values() if m.matches(config.get('base_url',''))
                       and m.settings['gateway_type'] == config.get('gateway_type','omniroute')]
            if len(matches) == 1: return matches[0]
            raise ValueError('This task uses a different OmniRoute endpoint or compatible gateway. Restore its original connection in Models.')
        if identity not in self.managers: raise ValueError('This saved gateway connection is unavailable')
        manager = self.managers[identity]
        if not manager.settings['enabled']: raise ValueError('This gateway connection is disabled in Models')
        return manager

    def capture(self, include=()):
        return [{**access_policy.snapshot(m.settings), 'connection_id':identity,
                 'gateway_type':m.settings['gateway_type'], 'name':m.settings['name'],
                 'automatic':m.settings.get('automatic', True)}
                for identity,m in tuple(self.managers.items()) if m.settings['enabled'] and (m.settings.get('automatic', True) or identity in include)]

    def for_policy(self, policy):
        manager = self.managers.get(policy['connection_id'])
        if not manager or not manager.settings['enabled']: return None
        if access_policy.snapshot(manager.settings) != access_policy.connection_policy(policy): return None
        return manager

    def shutdown(self):
        for manager in self.managers.values(): manager.shutdown()
