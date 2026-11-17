_EXECUTED_CODE = __import__('sys')._getframe().f_code
from .cli import main

if __name__ == '__main__':
    raise SystemExit(main())
