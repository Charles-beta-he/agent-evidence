"""Observation/readback pipeline. Internal admission is not accepted from disk."""
_EXECUTED_CODE = __import__('sys')._getframe().f_code
import time
from .contracts import keys, require
from .serialization import encode
from ._io import publish
from ._transport import call
from .receipts import now, receipt, outcome, reason, raw_digest, validate_outcome


def observe_check(request, output_fd, budget):
    start, tick = now(), time.monotonic()
    first = call(request, budget)
    keys(first, ('result','bytes_read')); validate_outcome(first['result'])
    raw = encode(receipt(request['context'], first['result'],start,now(),time.monotonic()-tick))
    publish(output_fd, request['receipt'], raw)
    readback = {**request,'phase':'readback','receipt_sha256':raw_digest(raw),
                'remaining_bytes':budget.left}
    second = call(readback,budget)
    keys(second, ('result','bytes_read')); validate_outcome(second['result'])
    return second['result']
