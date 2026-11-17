"""Bounded strict JSON. Errors are closed codes, never parser messages."""
_EXECUTED_CODE = __import__('sys')._getframe().f_code
import json
import math

CONTROL_LIMIT = 262144
REPORT_LIMIT = 8 * 1024 * 1024


class EvidenceError(ValueError):
    """Internal closed-code failure; never wrap arbitrary exception strings."""


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise EvidenceError('json_invalid')
        result[key] = value
    return result


def _reject(_):
    raise EvidenceError('json_invalid')


def _float(value):
    value = float(value)
    if not math.isfinite(value):
        raise EvidenceError('json_invalid')
    return value


def _shape(value, depth=0):
    if depth > 16:
        raise EvidenceError('control_limit')
    if isinstance(value, dict):
        if len(value) > 1024 or any(not isinstance(k, str) or len(k) > 128 for k in value):
            raise EvidenceError('control_limit')
        for item in value.values():
            _shape(item, depth + 1)
    elif isinstance(value, list):
        if len(value) > 1024:
            raise EvidenceError('control_limit')
        for item in value:
            _shape(item, depth + 1)
    elif isinstance(value, str):
        if len(value) > 4096:
            raise EvidenceError('control_limit')
    elif value is None or type(value) is bool:
        return
    elif type(value) is int:
        if abs(value) > 2**63 - 1:
            raise EvidenceError('control_limit')
    elif type(value) is float and math.isfinite(value):
        return
    else:
        raise EvidenceError('json_invalid')


def decode(raw, limit=CONTROL_LIMIT):
    if not isinstance(raw, bytes) or len(raw) > limit:
        raise EvidenceError('control_limit')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                           parse_float=_float, parse_constant=_reject)
        _shape(value)
        if not isinstance(value, dict):
            raise EvidenceError('json_not_object')
        return value
    except (ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, EvidenceError):
            raise
        raise EvidenceError('json_invalid') from None


def encode(value, *, limit=CONTROL_LIMIT):
    if type(limit) is not int or not 0 < limit <= REPORT_LIMIT:
        raise EvidenceError('control_limit')
    _shape(value)
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(raw) > limit:
        raise EvidenceError('control_limit')
    return raw
