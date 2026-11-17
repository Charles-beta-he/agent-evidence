"""Explicit adapters; no discovery, owner imports or registration side effects."""
_EXECUTED_CODE = __import__('sys')._getframe().f_code
