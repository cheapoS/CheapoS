"""Optional signed Club connection; never claims an offline upload succeeded."""
import copy
import hashlib
import json
import os
import threading
import urllib.request
import urllib.error
import uuid
from pathlib import Path
from datetime import datetime, timezone
from .credentials import CredentialStore
from .lifetime_usage import resolve_category, safe_model

DEFAULT_LEADERBOARD_URL = "https://cheapos.lol"

def now():
    return datetime.now(timezone.utc).isoformat()

def crypto():
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        return Ed25519PrivateKey, serialization
    except ImportError:
        raise ValueError("Club connections need the optional dependency: python3 -m pip install -r requirements-club.txt. Local work is unaffected.") from None

def extract_telemetry(summ, share_models=False):
    if not summ or not isinstance(summ, dict):
        return None
    healing = summ.get('self_healing_index') or {}
    models = summ.get('models') or {}
    total_reqs = sum(m.get('requests', 0) for m in models.values())
    total_succ = sum(m.get('successes', 0) for m in models.values())
    total_fail = sum(m.get('failures', 0) for m in models.values())
    total_secs = sum(m.get('total_seconds', 0.0) for m in models.values())
    avg_lat = round((total_secs / total_succ) * 1000) if total_succ > 0 else 0
    succ_rate = round((total_succ / (total_succ + total_fail)) * 100, 1) if (total_succ + total_fail) > 0 else 100.0
    fb = {}
    for m in models.values():
        for k, count in m.get('failure_breakdown', {}).items():
            safe_k = str(k)[:60]
            fb[safe_k] = fb.get(safe_k, 0) + int(count)

    pairs = []
    if share_models:
        for p in list((summ.get('model_pairs') or {}).values())[:10]:
            w = safe_model(p.get('worker'))
            rv = safe_model(p.get('reviewer'))
            if w and rv:
                pairs.append(dict(
                    worker=w[:160],
                    reviewer=rv[:160],
                    is_independent=bool(p.get('is_independent')),
                    total_jobs=int(p.get('total_jobs', 0)),
                    completion_rate=float(p.get('completion_rate', 0.0)),
                    avg_tokens_per_job=int(p.get('avg_tokens_per_job', 0))
                ))

    tok = summ.get('tokens') or {}
    task_types = summ.get('task_types') or {}
    types_clean = {
        k: dict(completed=int(v.get('completed', 0)), tokens=int(v.get('tokens', 0)))
        for k, v in task_types.items() if isinstance(v, dict)
    }

    tasks_by_role = summ.get('tasks_by_role') or {}
    roles_clean = {}
    for r, v in tasks_by_role.items():
        if isinstance(v, dict):
            m_map = {m[:160]: int(count) for m, count in (v.get('models') or {}).items()} if share_models else {}
            roles_clean[r] = dict(
                completed_tasks=int(v.get('completed_tasks', 0)),
                tokens=int(v.get('tokens', 0)),
                models=m_map
            )

    return dict(
        self_healing=dict(
            initial_work_tokens=int(healing.get('initial_work_tokens', 0)),
            recovery_tokens=int(healing.get('recovery_tokens', 0)),
            repair_overhead_pct=float(healing.get('repair_overhead_pct', 0.0))
        ),
        model_pairs=pairs,
        provider_health=dict(
            total_requests=total_reqs,
            successes=total_succ,
            failures=total_fail,
            success_rate=succ_rate,
            avg_latency_ms=avg_lat,
            failure_breakdown=fb
        ),
        token_depth=dict(
            reasoning_tokens=int(tok.get('reasoning', 0)),
            cached_tokens=int(tok.get('cached', 0))
        ),
        task_types=types_clean,
        tasks_by_role=roles_clean
    )

class ClubManager:
    def __init__(self, data_directory, leaderboard_url=None, credentials=None):
        self.directory=Path(data_directory)
        self.path=self.directory/'club_connection.json'
        self.leaderboard_url=(leaderboard_url or os.getenv('CHEAPOS_CLUB_URL') or DEFAULT_LEADERBOARD_URL).rstrip('/')
        from urllib.parse import urlsplit
        url=urlsplit(self.leaderboard_url)
        if url.scheme!='https' and not (url.scheme=='http' and url.hostname in {'127.0.0.1','localhost'}):
            raise ValueError('Club URL must use HTTPS or local development loopback.')
        self.credentials=credentials or CredentialStore(self.directory)
        self.lock=threading.RLock()
        self.stop=threading.Event()
        self.thread=None
        self.lifetime=None
        self._remote_profile_cache=None
        self._remote_profile_cache_time=0
        self._remote_profile_lock=threading.Lock()
        default=dict(installation_id=str(uuid.uuid4()),pairing_id=None,identity=None,sync_enabled=False,sequence=0,previous_hash='',baseline=[],sent={},pending=None,last_synced_at=None,error=None)
        self.blocked=None
        try:
            self.state=json.loads(self.path.read_text()) if self.path.exists() else default
            if not isinstance(self.state,dict) or not set(default).issubset(self.state): raise ValueError()
            self.state.setdefault('share_models',False)
            self.state.setdefault('endpoint',self.leaderboard_url)
            if self.state['endpoint']!=self.leaderboard_url:
                legacy={'https://cheapskate-club.vercel.app'}
                if self.state['endpoint'] in legacy and self.leaderboard_url==DEFAULT_LEADERBOARD_URL:
                    inst_id=self.state.get('installation_id')
                    if inst_id:
                        old_slot=self.state['endpoint']+'/installation/'+inst_id
                        new_slot=self.leaderboard_url+'/installation/'+inst_id
                        old_key=self.credentials.get(old_slot)
                        if old_key and not self.credentials.get(new_slot):
                            self.credentials.set(new_slot,old_key)
                    self.state['endpoint']=self.leaderboard_url
                    self._save()
                else:
                    raise ValueError()
        except (ValueError,OSError):
            self.blocked='Club connection settings could not be loaded. Restore the saved file or original endpoint; local work is unaffected.'
            self.state={**default,'error':self.blocked}

    def _save(self):
        if self.blocked: raise ValueError(self.blocked)
        self.directory.mkdir(parents=True,exist_ok=True)
        temporary=self.path.with_suffix('.tmp')
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as f:
            json.dump(self.state,f);f.flush();os.fsync(f.fileno())
        os.replace(temporary,self.path)

    def _key(self, create=False):
        if self.blocked: raise ValueError(self.blocked)
        key_type,serialization=crypto()
        slot=self.leaderboard_url+'/installation/'+self.state['installation_id']
        raw=self.credentials.get(slot)
        if not raw:
            if not create: raise ValueError('Club signing key is unavailable. Unlock your credential store; local work can continue.')
            key=key_type.generate()
            raw=key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption()).hex()
            self.credentials.set(slot,raw)
        return key_type.from_private_bytes(bytes.fromhex(raw))

    def _signed(self,message):
        _,serialization=crypto();key=self._key()
        payload=json.dumps(message,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)
        return dict(payload=payload,signature=key.sign(('cheapskate-club-v1\n'+payload).encode()).hex(),public_key=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw).hex())

    def _message(self,action,**fields):
        return dict(version=1,action=action,installation_id=self.state['installation_id'],pairing_id=self.state['pairing_id'],**fields)

    def _request(self,envelope):
        req=urllib.request.Request(self.leaderboard_url+'/api/installation',data=json.dumps(envelope).encode(),headers={'Content-Type':'application/json','User-Agent':'cheapoS/0.1.0'},method='POST')
        try:
            with urllib.request.urlopen(req,timeout=5) as response:
                return json.loads(response.read(65536))
        except urllib.error.HTTPError as error:
            try: code=json.loads(error.read(4096)).get('code')
            except (ValueError,OSError): code=None
            messages={
                'pairing_expired':'The approval link expired. Click Connect to Club for a fresh link.',
                'revoked':'This connection was revoked. Disconnect here, then connect the intended Club account.',
                'paused':'Sharing is paused at the Club. Enable sharing again to continue.',
                'already_connected':'This installation is already connected. Disconnect before switching accounts.',
                'key_mismatch':'The saved signing key does not match this installation. Restore its original credential; local work is unaffected.',
                'rate_limit':'Too many connection attempts. Try again in an hour; local work is unaffected.',
            }
            raise ValueError(messages.get(code,'Club setup or saved usage state needs attention. Check the website migration and server key, then retry. Local work is unaffected.')) from None
        except (OSError,ValueError,urllib.error.URLError):
            raise ValueError('Club is unavailable or rejected the connection. Saved usage is retained. Check your account connection and try again; local work can continue.') from None

    def _call(self,action,**fields):
        return self._request(self._signed(self._message(action,**fields)))

    def _heal_handle_from_status(self):
        """When cached handle returns 404, check installation status using cryptographic credentials to self-heal."""
        try:
            with self.lock:
                if not self.state.get('identity'):
                    return None
            result = self._call('status')
            if result.get('status') == 'connected' and result.get('handle'):
                with self.lock:
                    self.state.setdefault('identity', {})
                    self.state['identity']['handle'] = result['handle']
                    if result.get('name'):
                        self.state['identity']['name'] = result['name']
                    self._save()
                return result['handle'].lstrip('@').lower()
        except Exception:
            pass
        return None

    def get_remote_profile(self, force=False):
        """Fetch and cache the public member profile from the Club leaderboard."""
        with self.lock:
            identity=self.state.get('identity')
            if not identity or not identity.get('handle'):
                return None
            handle=identity['handle'].lstrip('@').lower()

        now_ts=datetime.now(timezone.utc).timestamp()
        with self._remote_profile_lock:
            if not force and self._remote_profile_cache and (now_ts - self._remote_profile_cache_time < 60):
                return self._remote_profile_cache

        try:
            url=f"{self.leaderboard_url}/api/profile/{handle}"
            req=urllib.request.Request(url,headers={'User-Agent':'cheapoS','Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=4) as response:
                if response.status==200:
                    data=json.loads(response.read(65536).decode('utf-8'))
                    with self._remote_profile_lock:
                        self._remote_profile_cache=data
                        self._remote_profile_cache_time=now_ts
                    return data
        except urllib.error.HTTPError as err:
            if err.code == 404:
                # Handle was likely renamed on the Club website!
                # Recover true identity via signed status check.
                new_handle = self._heal_handle_from_status()
                if new_handle and new_handle != handle:
                    try:
                        url=f"{self.leaderboard_url}/api/profile/{new_handle}"
                        req=urllib.request.Request(url,headers={'User-Agent':'cheapoS','Accept':'application/json'})
                        with urllib.request.urlopen(req,timeout=4) as response:
                            if response.status==200:
                                data=json.loads(response.read(65536).decode('utf-8'))
                                with self._remote_profile_lock:
                                    self._remote_profile_cache=data
                                    self._remote_profile_cache_time=now_ts
                                return data
                    except Exception:
                        pass
            with self._remote_profile_lock:
                if self._remote_profile_cache:
                    return self._remote_profile_cache
        except Exception:
            with self._remote_profile_lock:
                if self._remote_profile_cache:
                    return self._remote_profile_cache
        return None

    def get_status(self,summary_dict=None,include_remote=False):
        remote=self.get_remote_profile() if include_remote and self.state.get('identity') else self._remote_profile_cache
        with self.lock:
            s=self.state
            return dict(installation_id=s['installation_id'],installation_name='This cheapoS installation',is_linked=bool(s['identity']),x_identity=s['identity'],sync_enabled=s['sync_enabled'],share_models=s.get('share_models',False),last_synced_at=s['last_synced_at'],leaderboard_url=self.leaderboard_url,connect_url=self.leaderboard_url+'/connect?id='+str(s['pairing_id'] or ''),pairing_pending=bool(s['pairing_id'] and not s['identity']),sync_message=s.get('sync_message'),error=s.get('error'),pending=bool(s['pending']),remote_profile=remote)

    def start_pairing(self,lifetime):
        with self.lock:
            if self.state.get('revoking'): raise ValueError('Finish disconnecting the current Club account before switching.')
            if self.state['identity']: return self.get_status()
            self._key(create=True)
            if self.state['pairing_id']:
                try:
                    # Recover approval or reuse the same live pending session.
                    return self.check_pairing()
                except ValueError as error:
                    if 'approval link expired' not in str(error): raise
            previous=copy.deepcopy(self.state)
            self.state.update(pairing_id=str(uuid.uuid4()),baseline=[r['request_id'] for r in lifetime.raw_requests()],sent={},pending=None,error=None)
            try:
                result=self._call('pair')
                if result.get('status')!='pending': raise ValueError('Unexpected Club pairing response.')
                self._save()
            except Exception:
                self.state=previous
                raise
            legacy=self.directory/'club_profile.json'
            if legacy.exists(): legacy.unlink()
            return self.get_status()

    def check_pairing(self, force=False):
        with self.lock:
            if self.state['identity'] and not force: return self.get_status()
            result=self._call('status')
            if result.get('status')=='connected':
                self.state.update(pairing_id=result.get('pairing_id',self.state['pairing_id']),identity={'handle':result['handle'],'name':result['name'],'account_id':result['account_id']},sequence=result['sequence'],previous_hash=result['previous_hash'],error=None)
                self._save()
            return self.get_status()

    def link(self,data):
        raise ValueError('Manual secrets are no longer supported. Use Connect to Club and approve in your browser.')

    def _flush(self):
        pending=self.state['pending']
        if not pending: return
        result=self._request(pending['envelope'])
        payload=pending['envelope']['payload'];message=json.loads(payload)
        expected=hashlib.sha256(payload.encode()).hexdigest()
        if result.get('status')!='accepted' or result.get('sequence')!=message['sequence'] or result.get('hash')!=expected:
            raise ValueError('Club acknowledgment did not match the saved upload. Nothing was marked synced.')
        self.state.update(sequence=message['sequence'],previous_hash=expected,pending=None,error=None)
        if result.get('handle') and self.state.get('identity'):
            self.state['identity']['handle'] = result['handle']
            if result.get('name'):
                self.state['identity']['name'] = result['name']
        if message['action']=='sync':
            self.state['sent'].update(pending['fingerprints']);self.state['last_synced_at']=now()
        else:
            self.state['sync_enabled']=message['enabled']
            self.state['share_models']=message.get('share_models',self.state.get('share_models',False))
        self._save()

    def _queue(self,action,_fingerprints=None,**fields):
        self.state['pending']={'envelope':self._signed(self._message(action,sequence=self.state['sequence']+1,previous_hash=self.state['previous_hash'],**fields)), 'fingerprints':_fingerprints or {}}
        self._save()

    def set_sync(self,enabled,share_models=None):
        with self.lock:
            if not isinstance(enabled,bool): raise ValueError('Sharing must be true or false.')
            if share_models is not None and not isinstance(share_models,bool): raise ValueError('Model sharing must be true or false.')
            was_enabled=self.state['sync_enabled']
            if not self.state['identity'] or self.state.get('revoking'): raise ValueError('Connect a Club account first.')
            self.state['sync_enabled']=False;self._save()
            # Reconcile an uncertain acknowledgment without uploading a pending
            # batch after the operator has clicked Pause sharing.
            if self.state['pending']:
                pending=self.state['pending'];message=json.loads(pending['envelope']['payload'])
                remote=self._call('status')
                expected=hashlib.sha256(pending['envelope']['payload'].encode()).hexdigest()
                if remote.get('sequence')==message['sequence'] and remote.get('previous_hash')==expected:
                    if message['action']=='sync': self.state['sent'].update(pending['fingerprints'])
                    self.state.update(sequence=remote['sequence'],previous_hash=expected)
                elif remote.get('sequence')!=self.state['sequence'] or remote.get('previous_hash')!=self.state['previous_hash']:
                    raise ValueError('Club cursor conflicts with saved work. Sharing remains paused.')
                self.state['pending']=None;self._save()
            if enabled and not was_enabled and self.lifetime:
                # Requests begun before enabling/resuming sharing remain private.
                self.state['baseline']=list(set(self.state['baseline']) | {row['request_id'] for row in self.lifetime.raw_requests() if row['request_id'] not in self.state['sent']})
            fields={'enabled':enabled}
            if share_models is not None: fields['share_models']=share_models
            self._queue('consent',**fields);self._flush()
            if share_models is not None:
                self.state['sync_message']='Model names will be shared on your Club profile.' if share_models else 'Model sharing is off. Your token totals are unchanged.'
                self._save()
            if enabled: self.start_background(self.lifetime)
            return self.get_status()

    def sync_now(self,lifetime,period='all'):
        with self.lock:
            if not self.state['sync_enabled'] or self.state.get('revoking'): raise ValueError('Sharing is paused.')
            try:
                uploaded=len((self.state.get('pending') or {}).get('fingerprints',{}))
                self._flush()
                new_requests=0;waiting=0
                events=[];fingerprints={};baseline=set(self.state['baseline'])
                for row in lifetime.raw_requests():
                    rid=row['request_id']
                    if rid in baseline: continue
                    new_requests+=1
                    if not row.get('reconciled') or not row.get('date'):
                        waiting+=1;continue
                    if any(type(row.get(k)) not in (int,float) or row[k]<0 or row[k]>1000000000 or int(row[k])!=row[k] for k in ('input_tokens','output_tokens')):
                        waiting+=1;continue
                    event=dict(event_id=str(uuid.uuid5(uuid.UUID(self.state['installation_id']),rid)),category='paid' if (row.get('reported_cost') or 0)>0 else resolve_category(row),input_tokens=int(row['input_tokens']),output_tokens=int(row['output_tokens']),accounting_at=row['date']+'T00:00:00Z')
                    if row.get('reasoning_tokens') is not None and isinstance(row['reasoning_tokens'], (int, float)) and row['reasoning_tokens'] >= 0:
                        event['reasoning_tokens'] = int(row['reasoning_tokens'])
                    if row.get('cached_tokens') is not None and isinstance(row['cached_tokens'], (int, float)) and row['cached_tokens'] >= 0:
                        event['cached_tokens'] = int(row['cached_tokens'])
                    role=row.get('role')
                    if role in ('worker','reviewer','planner','coordinator'):
                        event['role']=role
                    elif role:
                        event['role']='unknown'
                    if self.state.get('share_models'):
                        model=safe_model(row.get('served_model') or row.get('requested_model'))
                        if model: event['model_name']=model[:160]
                    fingerprint=hashlib.sha256(json.dumps(event,sort_keys=True).encode()).hexdigest()
                    if self.state['sent'].get(rid)==fingerprint: continue
                    event['slot']=len(events);events.append(event);fingerprints[rid]=fingerprint
                    if len(events)==100: break
                queue_kwargs = None
                if events:
                    queue_kwargs = dict(_fingerprints=fingerprints, events=events)
                elif lifetime and hasattr(lifetime, 'summary'):
                    try:
                        summ = lifetime.summary('all')
                        comp = summ.get('completion') or {}
                        h_jobs = int(comp.get('human_accepted_jobs', 0))
                        m_runs = int(comp.get('merged_runs', 0))
                        r_jobs = int(comp.get('independent_review_approved_jobs', 0))
                        completed = h_jobs + m_runs
                        rate = round((completed / r_jobs * 100), 1) if r_jobs > 0 else None
                        current_outcomes = dict(
                            completed_tasks=completed,
                            human_accepted_jobs=h_jobs,
                            merged_runs=m_runs,
                            review_approved_jobs=r_jobs,
                            acceptance_rate=rate
                        )
                        telem = extract_telemetry(summ, share_models=bool(self.state.get('share_models')))
                        last_synced = self.state.get('last_synced_outcomes')
                        last_telem = self.state.get('last_synced_telemetry')
                        if (completed > 0 and current_outcomes != last_synced) or (telem and telem != last_telem):
                            queue_kwargs = dict(_fingerprints={}, events=[], work_outcomes=current_outcomes)
                            if telem: queue_kwargs['telemetry'] = telem
                    except Exception:
                        pass

                if queue_kwargs is not None:
                    if lifetime and hasattr(lifetime, 'summary'):
                        try:
                            summ = lifetime.summary('all')
                            if 'work_outcomes' not in queue_kwargs:
                                comp = summ.get('completion') or {}
                                h_jobs = int(comp.get('human_accepted_jobs', 0))
                                m_runs = int(comp.get('merged_runs', 0))
                                r_jobs = int(comp.get('independent_review_approved_jobs', 0))
                                completed = h_jobs + m_runs
                                rate = round((completed / r_jobs * 100), 1) if r_jobs > 0 else None
                                queue_kwargs['work_outcomes'] = dict(
                                    completed_tasks=completed,
                                    human_accepted_jobs=h_jobs,
                                    merged_runs=m_runs,
                                    review_approved_jobs=r_jobs,
                                    acceptance_rate=rate
                                )
                            if 'telemetry' not in queue_kwargs:
                                telem = extract_telemetry(summ, share_models=bool(self.state.get('share_models')))
                                if telem: queue_kwargs['telemetry'] = telem
                        except Exception:
                            pass
                    self._queue('sync', **queue_kwargs)
                    self._flush()
                    if queue_kwargs.get('work_outcomes'):
                        self.state['last_synced_outcomes'] = queue_kwargs['work_outcomes']
                    if queue_kwargs.get('telemetry'):
                        self.state['last_synced_telemetry'] = queue_kwargs['telemetry']
                    uploaded += len(queue_kwargs.get('events', []))
                self.state['sync_message']=(f'Uploaded {uploaded} usage records. Additional queued usage syncs automatically.' if uploaded else 'No new usage yet. Only requests made after sharing was enabled are uploaded.' if not new_requests else 'Waiting for complete token usage before uploading.' if waiting else 'Up to date. All eligible usage has already been uploaded.')
                self.state['error']=None
                self._save()
                return self.get_status()
            except ValueError as error:
                self.state['error']=str(error);self._save();raise

    def disconnect(self):
        with self.lock:
            self.state.update(sync_enabled=False,revoking=True);self._save()
            if self.state['pairing_id']:
                result=self._call('disconnect')
                if result.get('status')!='disconnected': raise ValueError('Club did not confirm disconnection. Sharing remains stopped.')
            self.state.update(identity=None,pairing_id=None,pending=None,sent={},baseline=[],revoking=False,error=None,share_models=False)
            self._save()
            with self._remote_profile_lock:
                self._remote_profile_cache=None
                self._remote_profile_cache_time=0
            return {'status':'disconnected'}

    def start_background(self,lifetime):
        self.lifetime=lifetime
        if not lifetime or not self.state['sync_enabled'] or self.thread and self.thread.is_alive(): return
        def run():
            delay=60
            while not self.stop.wait(delay):
                try:
                    if self.state['sync_enabled']: self.sync_now(lifetime)
                    delay=60
                except Exception:
                    delay=min(delay*2,900)
        self.thread=threading.Thread(target=run,daemon=True,name='club-sync');self.thread.start()

    def shutdown(self):
        self.stop.set()
