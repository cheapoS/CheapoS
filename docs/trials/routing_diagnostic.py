"""One targeted diagnostic per configured role through the real app gateway adapter."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from exporter_live import save, git, runtime_hash, fingerprint


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--app-repo',type=Path,default=Path(__file__).resolve().parents[2])
    args=parser.parse_args();app=args.app_repo.resolve();root=args.root.resolve()
    baseline=json.loads((root/'baseline.private.json').read_text())
    if git(app,'status','--porcelain') or git(app,'rev-parse','HEAD')!=baseline['app_sha'] or runtime_hash(app)!=baseline['runtime_hash']:
        parser.error('Use the clean frozen app from preparation')
    state=root/'state'
    if fingerprint(state,['config.json','preferences.json','gateway.json'])!=baseline['access_config']:parser.error('Configuration changed')
    fd=os.open(root/'diagnostic.intent',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    sys.path.insert(0,str(app))
    from cheapos.engine import Engine
    from cheapos.gateways import gateway_for
    from cheapos import access_policy, route_health, served_identity
    from cheapos.routing import PROBE_MESSAGES, PROBE_TOOL
    engine=Engine(state);results=[];started=time.monotonic()
    try:
        catalog=engine.gateway.catalog(fresh=True)
        if catalog['status']!='ready':raise ValueError('Catalog unavailable')
        policy=access_policy.snapshot(engine.gateway.settings)
        for role in ('worker','reviewer'):
            cfg=engine.config[role];model=next((m for m in catalog['models'] if m['id']==cfg['model']),None)
            result={'role':role,'requested_model':served_identity.safe_model(cfg['model']),
                    'served_model':None,'identity_provenance':'unknown','gateway_internal_attempts':'unavailable',
                    'gateway_fallback_disabled':False,'app_fallback_disabled':True,'qualified_pinned_model':False,
                    'requests':0,'usage':None,'status':'not_dispatched','output_token_allowance':1024}
            results.append(result);begin=time.monotonic()
            if not engine.gateway.matches(cfg['base_url']):raise ValueError('Configured diagnostic endpoint differs from authorized gateway')
            access_policy.guard({'access_policy':policy,'route':{'access_policy':policy}},cfg,engine.gateway.settings,catalog['models'])
            if not model or not access_policy.eligible(model,policy):result['status']='access_excluded';continue
            identity=route_health.probe_identity(cfg['base_url'],model,policy['connection_revision'])
            if engine.gateway.pool.observation(cfg['base_url'],cfg['model'],policy['connection_revision'])['cooling_down']:
                result['status']='cached_cooldown';continue
            if engine.gateway.pool.fresh_probe(cfg['base_url'],cfg['model'],policy['connection_revision'],identity):
                result['status']='cached_tool_support';continue
            result['requests']=1
            try:
                response,usage=gateway_for(cfg,engine.provider_key(role,cfg)).complete_brief(PROBE_MESSAGES,[PROBE_TOOL],1024,lambda *a:None,lambda:False)
                result['usage']={k:v for k,v in usage.items() if k in ('prompt_tokens','completion_tokens','total_tokens','cost') and isinstance(v,(int,float))}
                result.update({k:v for k,v in (usage.get('_served_identity') or {}).items() if k in ('served_model','identity_provenance')})
                route_health.validate_probe(response,engine.parse_call)
                result['status']='structured_tool_support'
                engine.gateway.pool.record(cfg['base_url'],cfg['model'],role,probe=True,connection_revision=policy['connection_revision'],probe_identity=identity)
            except Exception as error:
                result['status']='failed';result['failure_category']=route_health.classify(error)['category']
                usage=getattr(error,'usage',None)
                if result['usage'] is None and isinstance(usage,dict):
                    result['usage']={k:v for k,v in usage.items() if k in ('prompt_tokens','completion_tokens','total_tokens','cost') and isinstance(v,(int,float))}
                result['usage_uncertain']=result['usage'] is None
                engine.gateway.pool.record(cfg['base_url'],cfg['model'],role,error=error,connection_revision=policy['connection_revision'])
            finally:result['seconds']=time.monotonic()-begin
    finally:
        engine.shutdown()
        record={'app_sha':baseline['app_sha'],'phase':'targeted_gateway_diagnostic','results':results,
                'elapsed_seconds':time.monotonic()-started,'request_count':sum(r['requests'] for r in results),
                'billing_verified':False,'note':'Gateway fallback control/internal chain unavailable. These are configured-route diagnostics, not qualified pinned-model tests.'}
        save(root/'diagnostic.json',record);print(json.dumps(record,sort_keys=True))

if __name__=='__main__':main()
