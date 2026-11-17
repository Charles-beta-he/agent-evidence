"""Receipt identity and fresh time validation; no file reference authority."""
_EXECUTED_CODE = __import__('sys')._getframe().f_code
import hashlib
import time
from datetime import datetime, timezone
from .contracts import keys, require, identifier, digest
from .serialization import encode

REASONS = frozenset(('observed','json_invalid','json_not_object','control_limit',
    'target_missing','target_not_regular','hardlink_denied','target_too_large',
    'target_drift','boundary_invalid','input_unavailable','schema_invalid',
    'budget_exhausted','worker_timeout','worker_protocol','worker_output_limit',
    'policy_unknown_domain','policy_disabled','policy_invalid','policy_drift',
    'receipt_invalid','receipt_drift','revision_drift','source_drift','not_observed',
    'unsupported_platform','inventory_binding','inventory_revoked','inventory_expired',
    'inventory_not_live','inventory_already_frozen','inventory_already_observed',
    'inventory_drift','inventory_source_unverified','inventory_control_invalid','lock_drift'))


def reason(error):
    from .serialization import EvidenceError
    if isinstance(error, EvidenceError) and str(error) in REASONS:
        return str(error)
    if isinstance(error, FileNotFoundError):
        return 'target_missing'
    return 'input_unavailable'


def outcome(code, sha=None):
    require(code in REASONS)
    verdict = 'PASS' if code == 'observed' else 'FAIL' if code in ('json_invalid','json_not_object') else 'NOT_APPLICABLE' if code == 'policy_disabled' else 'UNKNOWN'
    return {'execution_state':'succeeded' if code == 'observed' else 'failed' if verdict == 'FAIL' else 'blocked',
            'evidence_state':'verified' if verdict in ('PASS','FAIL') else 'unavailable',
            'verdict':verdict, 'reason_code':code, 'observed_sha256':sha}


def validate_outcome(value):
    if isinstance(value, dict) and 'adapter' in value:
        from .adapters.hermes import validate_result
        validate_result(value['adapter'])
        require(value['reason_code'] == 'observed', 'worker_protocol')
        validate_outcome({k:v for k,v in value.items() if k != 'adapter'})
        return value
    keys(value, ('execution_state','evidence_state','verdict','reason_code','observed_sha256'))
    require(value['reason_code'] in REASONS, 'worker_protocol')
    sha = value['observed_sha256']
    if sha is not None:
        digest(sha)
    require(value == outcome(value['reason_code'],sha), 'worker_protocol')
    require((sha is not None) == (value['reason_code'] == 'observed'), 'worker_protocol')
    return value


def now():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    require(isinstance(value,str) and len(value) <= 40, 'receipt_invalid')
    try:
        parsed = datetime.fromisoformat(value)
        require(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0, 'receipt_invalid')
        return parsed.timestamp()
    except (ValueError,OverflowError):
        raise ValueError('receipt_invalid') from None


def context(value):
    keys(value, ('run_id','profile_id','system_id','check_id','target_id','operation',
                 'candidate_revision','check_revision','input_identity','output_identity','policy_sha256'))
    for key in ('run_id','profile_id','system_id','check_id','target_id'):
        identifier(value[key])
    for key in ('candidate_revision','check_revision','input_identity','output_identity','policy_sha256'):
        digest(value[key])
    require(value['operation'] in ('presence','json','hermes'))
    if value['operation'] == 'hermes':
        from .adapters.hermes import PAIRS, BLOCKED
        require((value['system_id'],value['check_id']) in PAIRS and value['check_id'] not in BLOCKED)


def receipt(ctx, result, start, end, duration):
    return {'schema':'agent_evidence_check_receipt_dev1','context':ctx,'result':result,
            'started_at':start,'finished_at':end,'duration_seconds':duration}


def validate_receipt(value, ctx):
    keys(value, ('schema','context','result','started_at','finished_at','duration_seconds'))
    require(value['schema'] == 'agent_evidence_check_receipt_dev1' and value['context'] == ctx, 'receipt_invalid')
    context(ctx); validate_outcome(value['result'])
    require(('adapter' in value['result']) == (ctx['operation']=='hermes' and value['result']['reason_code']=='observed'), 'receipt_invalid')
    start, finish = timestamp(value['started_at']), timestamp(value['finished_at'])
    require(start <= finish <= time.time() and time.time() - start <= 300, 'receipt_invalid')
    duration = value['duration_seconds']
    require(type(duration) in (int,float) and 0 <= duration <= 10, 'receipt_invalid')
    return value


def raw_digest(value):
    return hashlib.sha256(value).hexdigest()
