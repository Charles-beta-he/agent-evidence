import unittest
from agent_evidence.serialization import decode, encode, EvidenceError
from agent_evidence.contracts import combine


class Contracts(unittest.TestCase):
    def test_strict_json(self):
        for raw in (b'{"a":1,"a":2}', b'{"x":NaN}', b'{"x":1e999}', b'\xff', b'[]', b'['*40+b']'*40):
            with self.subTest(raw=raw), self.assertRaises(EvidenceError):
                decode(raw)
        self.assertEqual(decode(b'{"ok":true}'), {'ok': True})

    def test_limits(self):
        for value in ({'s': 'x'*4097}, {'a': list(range(1025))}):
            with self.assertRaises(EvidenceError):
                encode(value)

    def test_precedence(self):
        self.assertEqual(combine([]), 'UNKNOWN')
        self.assertEqual(combine(['NOT_APPLICABLE']), 'NOT_APPLICABLE')
        self.assertEqual(combine(['UNKNOWN', 'FAIL']), 'FAIL')
        self.assertEqual(combine(['PASS', 'NOT_APPLICABLE']), 'PASS')
        self.assertEqual(combine(['forged', 'PASS']), 'UNKNOWN')
