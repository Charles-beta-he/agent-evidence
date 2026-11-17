"""Synthetic-only fixture creation. Never overwrite an existing destination."""
_EXECUTED_CODE = __import__('sys')._getframe().f_code
from ._io import absolute, new_directory, directory, publish
from .serialization import encode


def fixture(out, *, inventory=False, procedures=False, hermes=False):
    absolute(out); new_directory(out)
    with directory(out) as fd:
        publish(fd,'sample.json',b'{"synthetic":true}')
        publish(fd,'policy.lock',b'')
        publish(fd,'policy.json',encode({'schema':'agent_evidence_policy_v1',
            'domains':{'demo':{'enabled':True,'epoch':1}}}))
        spec = {'schema':'agent_evidence_checks_dev1',
            'profile_id':'synthetic','candidate_revision':'a'*64,
            'targets':{'sample':{'path':'sample.json','domains':['demo']}},
            'checks':[{'system_id':'demo','check_id':operation,'target_id':'sample',
                       'operation':operation,'domains':[],'required':True} for operation in ('presence','json')],
            'policy':'policy.json','lock':'policy.lock'}
        if inventory or procedures:
            spec['schema'] = 'agent_evidence_inventory_run_v1'
            bundle = procedure_bundle() if procedures else None
            spec['inventory'] = _inventory_fixture(fd, bundle['declarations'] if bundle else None)
            if bundle:
                spec['schema'] = 'agent_evidence_procedure_run_v1'
                spec['procedures'] = 'procedures.json'
                publish(fd, 'procedures.json', encode(bundle))
        if hermes:
            from .adapters.hermes import PRESENCE
            import time
            current = time.time()
            job = {'id':'synthetic-job','enabled':True,'state':'scheduled',
                'schedule':{'kind':'interval','minutes':10},'last_status':'ok',
                'last_run_at':current-10,'next_run_at':current+600,
                'execution_error':False,'delivery_error':False,'deliver':'local',
                'script':'experience_ratchet_watchdog.py','no_agent':True}
            exports = {
                'jobs':{'schema':'agent_evidence_hermes_jobs_v1','jobs':[job,
                    {**job,'id':'synthetic-memory','script':'memory_hygiene_dream_cron.sh'},
                    {**job,'id':'synthetic-delivery','script':None,'deliver':'telegram'}]},
                'heartbeat':{'schema':'agent_evidence_hermes_heartbeat_v1','heartbeat_at':current-1,'success_at':current-2},
                'proposal':{'schema':'agent_evidence_hermes_proposal_v1','observed_at':current-1,
                    'entry_count':0,'write_blocked':True,'auto_trim_memory':False},
                'status':{'schema':'agent_evidence_hermes_status_v1','dirty':False,'record_count':0}}
            for key, value in exports.items():
                publish(fd,key+'.json',encode(value))
                spec['targets'][key] = {'path':key+'.json','domains':['demo']}
            spec['schema'] = 'agent_evidence_hermes_run_v1'
            spec['checks'] = []
            spec['hermes'] = {'schema':'agent_evidence_hermes_inputs_v1',
                'inputs':{**{k:k for k in exports}, **{k:'sample' for k in PRESENCE}}}
        publish(fd, 'manifest.json', encode(spec))


def _inventory_fixture(fd, declarations=None):
    from datetime import datetime, timezone, timedelta
    from .receipts import raw_digest
    current = datetime.now(timezone.utc)
    declarations = declarations or {'schema':'agent_evidence_inventory_declarations_v1', 'procedures':[
        {'procedure_id':'demo-procedure', 'system_id':'demo', 'required':True,
         'exempt':False, 'source_ids':['sample'], 'domains':['demo']}]}
    common = {'owner_id':'synthetic-owner', 'evidence_id':'synthetic-scope', 'basis_id':'synthetic-review',
              'reviewed_at':(current-timedelta(seconds=1)).isoformat(),
              'expires_at':(current+timedelta(hours=1)).isoformat(), 'revoked':False,
              'max_freshness_seconds':7200, 'declarations_sha256':raw_digest(encode(declarations)),
              'procedure_ids':['demo-procedure'], 'source_pins':{'sample':raw_digest(b'{"synthetic":true}')}}
    scope = {**common, 'schema':'agent_evidence_inventory_scope_v1', 'scope_complete':True,
             'negative_boundaries':['not-business-certification']}
    approval = raw_digest(encode(scope))
    attestation = {**common, 'schema':'agent_evidence_inventory_attestation_v1',
                   'scope_complete':True, 'approved_scope_sha256':approval}
    catalog = {**common, 'schema':'agent_evidence_inventory_catalog_v1',
               'approved_scope_sha256':approval, 'source_domains':{'sample':['demo']}}
    values = dict(declarations=declarations, scope=scope, attestation=attestation, catalog=catalog)
    for name, value in values.items():
        publish(fd, name+'.json', encode(value))
    return {name:name+'.json' for name in values}


def procedure_bundle():
    """Fresh synthetic assertions; NOT receipts from business execution."""
    from datetime import datetime, timezone, timedelta
    from .receipts import raw_digest
    current = datetime.now(timezone.utc)
    def at(seconds):
        return (current + timedelta(seconds=seconds)).isoformat()
    declaration = {'procedure_id':'demo-procedure', 'system_id':'demo', 'required':True,
        'exempt':False, 'source_ids':['sample'], 'domains':['demo'],
        'validation':{'implementation_state':'enabled', 'freshness_seconds':3600,
            'min_successes':1, 'acceptance_atoms':['observed'],
            'negative_assertions':['no-extra-effect'], 'allowed_side_effects':[],
            'issuer':'synthetic-issuer', 'action':'execute_live_e2e_validation', 'scope':'demo-procedure'}}
    admitted = {}
    def store(key, record):
        raw = encode(record); admitted[key] = raw.decode('utf-8')
        return {'id':key, 'sha256':raw_digest(raw)}
    identity = {'receipt_id':'synthetic-receipt', 'procedure_id':'demo-procedure', 'system_id':'demo'}
    grant = store('synthetic-grant', {'schema':'agent_evidence_procedure_grant_v1', **identity,
        'grant_id':'synthetic-grant', 'issuer':'synthetic-issuer',
        'action':'execute_live_e2e_validation', 'scope':'demo-procedure', 'status':'active',
        'valid_from':at(-60), 'expires_at':at(3600)})
    def assertion(kind, name):
        return store(kind+'-evidence', {'schema':'agent_evidence_assertion_v1', **identity,
            'kind':kind, 'name':name, 'status':'PASS'})
    receipt = {'schema':'agent_evidence_procedure_receipt_v1', **identity,
        'declaration_sha256':raw_digest(encode(declaration)), 'started_at':at(-2), 'completed_at':at(-1),
        'result':'PASS', 'execution_mode':'live_e2e', 'grant':grant,
        'acceptance':{'observed':assertion('acceptance','observed')},
        'negative':{'no-extra-effect':assertion('negative','no-extra-effect')},
        'cleanup':assertion('cleanup','cleanup'), 'side_effects_observed':[]}
    return {'schema':'agent_evidence_procedure_bundle_v1',
        'declarations':{'schema':'agent_evidence_inventory_declarations_v1','procedures':[declaration]},
        'receipts':[receipt], 'admitted_evidence':admitted}

