"""Private fixed worker protocol. No input-selected executable or imports."""
_EXECUTED_CODE = __import__('sys')._getframe().f_code
import sys
import time
from .contracts import Budget, keys, member, ids, require, digest
from .serialization import decode, encode, EvidenceError, CONTROL_LIMIT
from ._io import directory, identity, read
from .policy import locked, snapshot, admit
from .receipts import context, outcome, reason, raw_digest, validate_receipt
from .revisions import revision


def observe(root_fd, request, budget):
    with locked(root_fd, request['lock'], budget, request['lock_identity']):
        policy, pin = snapshot(root_fd, request['policy'], budget)
        require(pin == request['context']['policy_sha256'], 'policy_drift')
        admit(policy, request['domains'])
        raw = read(root_fd, request['target'], budget)
        result = outcome('observed', raw_digest(raw))
        if request['context']['operation'] == 'json':
            try:
                decode(raw, limit=1048576)
            except EvidenceError as error:
                result = outcome(reason(error))
        if request['context']['operation'] == 'hermes':
            from .adapters.hermes import evaluate_pair, PRESENCE
            ctx = request['context']
            try:
                value = raw if ctx['check_id'] in PRESENCE else decode(raw, limit=1048576)
                result['adapter'] = evaluate_pair(ctx['system_id'], ctx['check_id'], value)
            except EvidenceError:
                from .adapters.hermes import result as adapter_result
                result['adapter'] = adapter_result('export_invalid')
        _, final_pin = snapshot(root_fd, request['policy'], budget)
        require(pin == final_pin, 'policy_drift')
        return result


def perform(request):
    keys(request, ('phase','input_root','output_root','context','policy','lock','target',
                   'domains','deadline','remaining_bytes','receipt','receipt_sha256','lock_identity'))
    digest(request['lock_identity'])
    require(request['phase'] in ('observe','readback'))
    context(request['context'])
    for key in ('policy','lock','target','receipt'):
        member(request[key])
    ids(request['domains'])
    require(type(request['deadline']) in (int,float) and 0 < request['deadline'] - time.monotonic() <= 10)
    require(type(request['remaining_bytes']) is int and 0 < request['remaining_bytes'] <= 8*1024*1024)
    budget = Budget(request['deadline'], request['remaining_bytes'])
    initial = budget.left
    try:
        require(request['context']['check_revision'] == revision(), 'revision_drift')
        with directory(request['input_root']) as source:
            require(identity(source) == request['context']['input_identity'], 'boundary_invalid')
            if request['phase'] == 'readback':
                digest(request['receipt_sha256'])
                with directory(request['output_root']) as output:
                    require(identity(output) == request['context']['output_identity'], 'boundary_invalid')
                    raw = read(output,request['receipt'],budget,CONTROL_LIMIT)
                    require(raw_digest(raw) == request['receipt_sha256'], 'receipt_drift')
                    prior = validate_receipt(decode(raw),request['context'])
                result = observe(source,request,budget)
                require(result == prior['result'], 'source_drift')
            else:
                require(request['receipt_sha256'] is None)
                result = observe(source,request,budget)
        budget.tick()
        require(request['context']['check_revision'] == revision(), 'revision_drift')
    except (OSError,ValueError,TypeError):
        error = sys.exception()
        result = outcome(reason(error))
    return {'result':result, 'bytes_read':initial-budget.left}


def main():
    try:
        raw = sys.stdin.buffer.read(CONTROL_LIMIT + 1)
        request = decode(raw)
        result = perform(request)
        sys.stdout.buffer.write(encode(result)); sys.stdout.buffer.flush()
        return 0
    except (OSError,ValueError,TypeError,KeyError):
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
