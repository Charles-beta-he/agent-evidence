"""Explicit development CLI. No HOME, environment discovery or hidden inputs."""
_EXECUTED_CODE = __import__('sys')._getframe().f_code
import argparse
import sys
from .serialization import encode, REPORT_LIMIT
from .receipts import reason


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's usual errors echo arbitrary user-controlled strings.
        self.exit(2, 'invalid_invocation\n')


def main(argv=None):
    parser = Parser(prog='agent-evidence', description='Bounded scoped evidence validation; not production certification.')
    sub = parser.add_subparsers(dest='command',required=True,parser_class=Parser)
    fixture_parser = sub.add_parser('fixture')
    fixture_parser.add_argument('--out',required=True)
    fixture_parser.add_argument('--inventory',action='store_true')
    fixture_parser.add_argument('--procedures',action='store_true')
    fixture_parser.add_argument('--hermes',action='store_true')
    evaluate_parser = sub.add_parser('evaluate')
    evaluate_parser.add_argument('--input-root',required=True)
    evaluate_parser.add_argument('--bundle',required=True)
    run_parser = sub.add_parser('run')
    run_parser.add_argument('--input-root',required=True)
    run_parser.add_argument('--manifest',required=True)
    run_parser.add_argument('--output-root',required=True)
    hermes_parser = sub.add_parser('hermes')
    hermes_sub = hermes_parser.add_subparsers(dest='hermes_command',required=True,parser_class=Parser)
    hermes_run = hermes_sub.add_parser('run')
    hermes_run.add_argument('--input-root',required=True)
    hermes_run.add_argument('--manifest',required=True)
    hermes_run.add_argument('--output-root',required=True)
    args = parser.parse_args(argv)
    try:
        from ._io import supported
        supported()
        if args.command == 'fixture':
            from .fixtures import fixture
            fixture(args.out, inventory=args.inventory, procedures=args.procedures, hermes=args.hermes)
            print('{"fixture_created":true}')
            return 0
        if args.command == 'evaluate':
            from ._io import directory, read
            from .contracts import Budget
            from .serialization import decode, CONTROL_LIMIT
            from .projections import evaluate_supplied
            with directory(args.input_root) as root:
                report = evaluate_supplied(decode(read(root, args.bundle, Budget.start(), CONTROL_LIMIT)))
            sys.stdout.buffer.write(encode(report) + b'\n')
            return 1
        from .runner import run_checks
        report = run_checks(args.input_root,args.manifest,args.output_root,hermes=args.command=='hermes')
        sys.stdout.buffer.write(encode(report, limit=REPORT_LIMIT) + b'\n')
        return 0 if report['complete'] else 1
    except (OSError,ValueError,TypeError,KeyError) as error:
        sys.stderr.write(reason(error) + '\n')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
