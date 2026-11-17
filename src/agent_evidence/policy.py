"""Read-only cooperative policy; never create a missing lock or policy."""
_EXECUTED_CODE = __import__('sys')._getframe().f_code
import fcntl
import hashlib
from contextlib import contextmanager
from ._io import leaf, read, identity
from .contracts import keys, identifier, require
from .serialization import decode, EvidenceError


def snapshot(root_fd, path, budget):
    raw = read(root_fd, path, budget, 65536)
    try:
        value = decode(raw)
    except EvidenceError:
        raise EvidenceError('policy_invalid') from None
    keys(value, ('schema','domains'))
    require(value['schema'] == 'agent_evidence_policy_v1', 'policy_invalid')
    require(isinstance(value['domains'],dict) and len(value['domains']) <= 1024, 'policy_invalid')
    for domain, row in value['domains'].items():
        identifier(domain); keys(row, ('enabled','epoch'))
        require(type(row['enabled']) is bool and type(row['epoch']) is int and row['epoch'] >= 0, 'policy_invalid')
    return value, hashlib.sha256(raw).hexdigest()


@contextmanager
def locked(root_fd, path, budget, expected_identity=None):
    budget.tick()
    with leaf(root_fd, path) as fd:
        pin = identity(fd)
        require(expected_identity is None or pin == expected_identity, 'lock_drift')
        # Cooperative writers MUST lock this same inode; never replace the lock.
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        try:
            budget.tick()
            yield pin
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)


def admit(value, domains):
    require(all(d in value['domains'] for d in domains), 'policy_unknown_domain')
    require(all(value['domains'][d]['enabled'] for d in domains), 'policy_disabled')


def dependencies(spec, target_id):
    result = set(spec['targets'][target_id]['domains'])
    for check in spec['checks']:
        if check['target_id'] == target_id:
            result.update(check['domains'])
    return sorted(result)
