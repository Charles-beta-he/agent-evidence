"""Sanitized v1 exports, not compatibility with an entire Hermes release.

Pure translation of caller-supplied metadata. Never opens refs, imports owners,
resolves destinations, executes scripts or certifies business runs.
"""
_EXECUTED_CODE = __import__('sys')._getframe().f_code
import math
import time
from ..contracts import require, keys, identifier
from ..receipts import timestamp

FIXED_CHECKS = {
    'hermes-core': ('hermes_doctor', 'post_update_check', 'dirty_worktree_awareness'),
    'cron': ('cron_list_readback', 'cron_error_cluster_watch', 'cron_ticker_heartbeat_watch',
             'gateway_manual_restart_rogue_watch'),
    'delivery:local': ('delivery_job_config_readback', 'delivery_failure_watch', 'cron_output_readback'),
    'delivery:telegram': ('delivery_job_config_readback', 'delivery_failure_watch'),
    'experience-ratchet': ('experience_ratchet_cli_present', 'experience_ratchet_watchdog_script_present',
                           'experience_ratchet_watchdog_cron'),
    'memory-hygiene-dream': ('memory_hygiene_dream_script_present', 'memory_hygiene_dream_cron_wrapper_present',
                            'memory_hygiene_dream_cron', 'memory_hygiene_dream_latest_proposal_readback'),
    'model-providers': ('provider_static_readiness', 'provider_health_watch'),
}
PAIRS = tuple((sid,cid) for sid, checks in FIXED_CHECKS.items() for cid in checks)
BLOCKED = {
    'hermes_doctor':'native_execution_disallowed',
    'post_update_check':'full_post_update_execution_disallowed',
    'gateway_manual_restart_rogue_watch':'process_identity_unavailable',
    'cron_output_readback':'run_output_identity_unavailable',
    'provider_static_readiness':'provider_static_unbound',
    'provider_health_watch':'provider_execution_disallowed',
}
PRESENCE = frozenset(('experience_ratchet_cli_present','experience_ratchet_watchdog_script_present',
                     'memory_hygiene_dream_script_present','memory_hygiene_dream_cron_wrapper_present'))
SCRIPTS = {'experience-ratchet':'experience_ratchet_watchdog.py',
           'memory-hygiene-dream':'memory_hygiene_dream_cron.sh'}
PLATFORMS = frozenset(('telegram','discord','slack','whatsapp','signal','matrix','mattermost',
    'homeassistant','dingtalk','feishu','wecom','wecom_callback','weixin','sms','email',
    'webhook','bluebubbles','qqbot','yuanbao'))
INPUT_KEYS = frozenset(('jobs','heartbeat','proposal','status',*PRESENCE))
REASON_VERDICTS = {
    **{v:'UNKNOWN' for v in BLOCKED.values()},
    'input_missing':'UNKNOWN','export_invalid':'UNKNOWN','duplicate_job_id':'FAIL',
    'cron_list_structure':'PASS','cron_recent_failure':'FAIL','cron_evidence_incomplete':'UNKNOWN',
    'cron_recent_results':'PASS','registration_missing':'UNKNOWN','registration_conflict':'FAIL',
    'registration_unresolved':'UNKNOWN','registration_structure':'PASS',
    'delivery_config_unresolved':'UNKNOWN','delivery_config_structure':'PASS',
    'run_route_identity_unavailable':'UNKNOWN','heartbeat_fresh':'PASS','heartbeat_stale':'FAIL',
    'source_time_invalid':'UNKNOWN','proposal_unsafe':'FAIL','proposal_producer_unbound':'UNKNOWN',
    'proposal_expired':'UNKNOWN','status_producer_unbound':'UNKNOWN','presence_only':'PASS',
}
COUNT_KEYS = frozenset(('matching_count','effective_active_count','disabled_count','paused_count',
    'completed_count','unknown_state_count','historical_observed_failures','recent_execution_failures',
    'active_recent_execution_failures','scheduling_failures','stale_results','unknown_results',
    'unknown_next_run_count','overdue_next_run_count','unresolved_route_count','job_count','entry_count'))
SEMANTICS = frozenset(('structure_not_schedule_health','registration_not_execution',
    'configuration_not_delivery','delivery_outcome_unverified','timestamps_not_writer_or_job_success',
    'supplied_status_not_git_acquisition','presence_not_execution','records_not_complete_event_history',
    'proposal_metadata_not_producer'))


def result(code, **metadata):
    return {'verdict':REASON_VERDICTS[code], 'reason_code':code, 'metadata':metadata}


def validate_result(value):
    keys(value, ('verdict','reason_code','metadata'))
    require(value['reason_code'] in REASON_VERDICTS)
    require(value['verdict'] == REASON_VERDICTS[value['reason_code']])
    meta=value['metadata']; require(isinstance(meta,dict))
    for key, val in meta.items():
        if key == 'semantics': require(val in SEMANTICS)
        else: require(key in COUNT_KEYS and type(val) is int and 0 <= val <= 1000000)
    return value


def input_key(sid, cid):
    if cid in BLOCKED: return None
    if cid in PRESENCE: return cid
    return {'dirty_worktree_awareness':'status','cron_ticker_heartbeat_watch':'heartbeat',
            'memory_hygiene_dream_latest_proposal_readback':'proposal'}.get(cid,'jobs')


def route(value):
    """Destination-free string/list/comma syntax. Never resolve origin or all."""
    malformed = unresolved = False
    if value is None or value == '': value = 'local'
    if isinstance(value,list):
        malformed=any(not isinstance(v,str) for v in value)
        value=','.join(v.strip() for v in value if isinstance(v,str) and v.strip()) or 'local'
    if not isinstance(value,str) or len(value)>1024:
        return {'platforms':[], 'malformed':True,'unresolved':False}
    tokens=[v.strip() for v in value.split(',') if v.strip()]
    platforms=set()
    for token in tokens:
        if token == 'local': platforms.add('local')
        elif token == 'origin' or token.lower() == 'all': unresolved=True
        elif token.lower() in PLATFORMS: platforms.add(token.lower())
        elif token.partition(':')[0].lower() in PLATFORMS:
            # Destination-bearing tokens are outside v1, but an explicitly
            # external platform still proves a local-only registration conflict.
            platforms.add(token.partition(':')[0].lower()); malformed=True
        else: malformed=True
    return {'platforms':sorted(platforms),'malformed':malformed or not tokens,'unresolved':unresolved}


def state(job):
    value=job.get('state')
    if value is None or isinstance(value,str) and not value.strip():
        return 'scheduled' if job.get('enabled',True) else 'paused'
    return value.strip() if isinstance(value,str) and value.strip() in ('scheduled','error','paused','completed') else None


def active(job):
    return job.get('enabled',True) and state(job) in ('scheduled','error')


def epoch(value):
    if isinstance(value,str): return timestamp(value)
    require(type(value) in (int,float) and math.isfinite(value) and value>=0)
    return float(value)


def schedule(value):
    if not isinstance(value,dict): return False
    kind=value.get('kind')
    if kind=='interval':
        return set(value)=={'kind','minutes'} and type(value['minutes']) is int and 0<value['minutes']<=525600
    if kind=='once':
        if set(value)!={'kind','run_at'}: return False
        epoch(value['run_at']); return True
    if kind!='cron' or set(value)!={'kind','expr'} or not isinstance(value['expr'],str) or len(value['expr'])>256: return False
    fields=value['expr'].split()
    if len(fields) not in (5,6): return False
    for field,(low,high) in zip(fields,((0,59),(0,23),(1,31),(1,12),(0,7),(1970,9999))):
        for part in field.split(','):
            parts=part.split('/')
            if len(parts)>2 or len(parts)==2 and not 1<=int(parts[1])<=high-low+1: return False
            if parts[0]!='*':
                ends=[int(n) for n in parts[0].split('-')]
                if len(ends) not in (1,2) or not low<=ends[0]<=ends[-1]<=high: return False
    return True


def job_records(value):
    keys(value,('schema','jobs')); require(value['schema']=='agent_evidence_hermes_jobs_v1')
    rows=value['jobs']; require(isinstance(rows,list) and len(rows)<=512)
    seen=set(); duplicate=False
    allowed={'id','enabled','state','schedule','last_status','last_run_at','next_run_at',
             'execution_error','delivery_error','deliver','script','no_agent'}
    for row in rows:
        require(isinstance(row,dict) and {'id','schedule'}<=set(row)<=allowed)
        identifier(row['id']); duplicate |= row['id'] in seen; seen.add(row['id'])
        require(type(row.get('enabled',True)) is bool and schedule(row['schedule']))
        # Semantic ambiguity is retained below; arbitrary body fields never pass.
        require(row.get('script') is None or isinstance(row['script'],str) and len(row['script'])<=128)
    return rows,duplicate


def health(rows,current):
    meta={key:0 for key in COUNT_KEYS if key not in ('unresolved_route_count','job_count','entry_count')}
    meta['matching_count']=len(rows)
    for job in rows:
        s=state(job); enabled=job.get('enabled',True); live=active(job)
        meta['effective_active_count']+=bool(live)
        meta['disabled_count']+=not enabled
        meta['paused_count']+=s=='paused'; meta['completed_count']+=s=='completed'
        meta['unknown_state_count']+=s is None
        bad=job.get('last_status')=='error' or job.get('execution_error') is True or job.get('delivery_error') is True
        meta['historical_observed_failures']+=bad
        try: age=current-epoch(job.get('last_run_at'))
        except (ValueError,TypeError,OverflowError): age=-1
        fresh=0<=age<=86400
        meta['recent_execution_failures']+=bool(bad and fresh)
        if not live: continue
        meta['active_recent_execution_failures']+=bool(bad and fresh)
        meta['scheduling_failures']+=s=='error'; meta['stale_results']+=age>86400
        meta['unknown_results']+=bool(age<0 or job.get('last_status') not in ('ok','error') or
            any(type(job.get(k)) is not bool for k in ('execution_error','delivery_error')))
        try: meta['overdue_next_run_count']+=epoch(job.get('next_run_at'))<current
        except (ValueError,TypeError,OverflowError): meta['unknown_next_run_count']+=1
    return meta


def evaluate_pair(system_id, check_id, value):
    """Pure supplied-value semantics. No I/O, admission or business certification."""
    require((system_id,check_id) in PAIRS)
    if check_id in BLOCKED: return result(BLOCKED[check_id])
    if value is None: return result('input_missing')
    current=time.time()
    try:
        if check_id in PRESENCE:
            require(isinstance(value,bytes))
            return result('presence_only',semantics='presence_not_execution')
        if check_id=='dirty_worktree_awareness':
            keys(value,('schema','dirty','record_count'))
            require(value['schema']=='agent_evidence_hermes_status_v1' and type(value['dirty']) is bool)
            require(type(value['record_count']) is int and 0<=value['record_count']<=1000000)
            return result('status_producer_unbound',semantics='supplied_status_not_git_acquisition')
        if check_id=='cron_ticker_heartbeat_watch':
            keys(value,('schema','heartbeat_at','success_at'))
            require(value['schema']=='agent_evidence_hermes_heartbeat_v1')
            hb,success=epoch(value['heartbeat_at']),epoch(value['success_at'])
            if hb>current or success>current: return result('source_time_invalid')
            stale=current-hb>=180 or hb-success>120 or current-success>=180
            return result('heartbeat_stale' if stale else 'heartbeat_fresh',semantics='timestamps_not_writer_or_job_success')
        if check_id=='memory_hygiene_dream_latest_proposal_readback':
            keys(value,('schema','observed_at','entry_count','write_blocked','auto_trim_memory'))
            require(value['schema']=='agent_evidence_hermes_proposal_v1')
            require(type(value['entry_count']) is int and 0<=value['entry_count']<=1000000)
            require(type(value['write_blocked']) is bool and type(value['auto_trim_memory']) is bool)
            if not value['write_blocked'] or value['auto_trim_memory']: return result('proposal_unsafe')
            age=current-epoch(value['observed_at'])
            if age<0: return result('source_time_invalid')
            if age>172800: return result('proposal_expired')
            return result('proposal_producer_unbound',entry_count=value['entry_count'],semantics='proposal_metadata_not_producer')
        rows,duplicate=job_records(value)
        if duplicate:
            return result('run_route_identity_unavailable' if check_id=='delivery_failure_watch' else 'duplicate_job_id')
        routes=[route(row.get('deliver')) for row in rows]
        if check_id=='cron_list_readback':
            return result('export_invalid' if any(r['malformed'] for r in routes) else 'cron_list_structure',
                          job_count=len(rows),semantics='structure_not_schedule_health')
        if check_id.endswith('_cron'):
            matched=[row for row in rows if row.get('script')==SCRIPTS[system_id]]
            if not matched: return result('registration_missing')
            mapped=[route(row.get('deliver')) for row in matched]
            conflict=any(not row.get('enabled',True) or row.get('no_agent') is not True for row in matched)
            conflict |= any(set(r['platforms'])-{'local'} for r in mapped)
            ambiguous=any(r['malformed'] or r['unresolved'] for r in mapped) or any(not active(row) or state(row)=='error' for row in matched)
            return result('registration_conflict' if conflict else 'registration_unresolved' if ambiguous else 'registration_structure',
                          **health(matched,current),semantics='registration_not_execution')
        matched=rows
        if system_id.startswith('delivery:'):
            matched=[row for row,r in zip(rows,routes) if system_id.split(':')[1] in r['platforms']]
        meta=health(matched,current)
        uncertain=sum(bool(r['malformed'] or r['unresolved']) for r in routes)
        meta['unresolved_route_count']=uncertain
        if check_id=='delivery_failure_watch':
            return result('run_route_identity_unavailable',**meta,semantics='delivery_outcome_unverified')
        if check_id=='delivery_job_config_readback':
            return result('delivery_config_unresolved' if uncertain or meta['unknown_state_count'] or not meta['effective_active_count'] else 'delivery_config_structure',
                          **meta,semantics='configuration_not_delivery')
        failed=meta['active_recent_execution_failures'] or meta['scheduling_failures']
        incomplete=uncertain or not meta['effective_active_count'] or any(meta[k] for k in
            ('unknown_state_count','stale_results','unknown_results','unknown_next_run_count','overdue_next_run_count'))
        return result('cron_recent_failure' if failed else 'cron_evidence_incomplete' if incomplete else 'cron_recent_results',
                      **meta,semantics='records_not_complete_event_history')
    except (ValueError,TypeError,KeyError,OverflowError):
        return result('export_invalid')


def evaluate_inputs(inputs):
    """21 required rows from an explicit map of already supplied values, no reads."""
    require(isinstance(inputs,dict) and set(inputs)<=INPUT_KEYS)
    return [dict(system_id=sid,check_id=cid,required=True,
                 **evaluate_pair(sid,cid,inputs.get(input_key(sid,cid)) if input_key(sid,cid) else None))
            for sid,cid in PAIRS]


def prepare(spec):
    """Translate explicit target IDs, never path discovery or blocked probes."""
    keys(spec['hermes'],('schema','inputs'))
    require(spec['hermes']['schema']=='agent_evidence_hermes_inputs_v1')
    bindings=spec['hermes']['inputs']
    require(isinstance(bindings,dict) and set(bindings)<=INPUT_KEYS)
    for target in bindings.values():
        identifier(target); require(target in spec['targets'])
    return [dict(system_id=sid,check_id=cid,target_id=bindings[key],operation='hermes',domains=[],required=True)
            for sid,cid in PAIRS if (key:=input_key(sid,cid)) in bindings]


def project(rows):
    """No post-freeze reads and no disabled fallback after failed final reads."""
    indexed={(r['system_id'],r['check_id']):r for r in rows}
    projected=[]
    for sid,cid in PAIRS:
        row=indexed.get((sid,cid))
        if row is None:
            value=result(BLOCKED[cid] if cid in BLOCKED else 'input_missing')
        elif 'adapter' in row and (row['reason_code']=='observed' or (
                row['verdict']=='FAIL' and row['evidence_state']=='verified'
                and row['adapter']['verdict']=='FAIL')):
            value=row['adapter']
        else:
            value={'verdict':row['verdict'],'reason_code':row['reason_code'],'metadata':{}}
        projected.append(dict(system_id=sid,check_id=cid,required=True,**value))
    from ..contracts import combine
    return {'schema':'agent_evidence_hermes_report_v1','checks':projected,'required_count':21,
            'gap_count':sum(r['verdict']!='PASS' for r in projected),
            'verdict':combine(r['verdict'] for r in projected),'certified_healthy':False}
