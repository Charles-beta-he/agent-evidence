"""Fixed isolated worker; nonblocking stdin AND stdout/stderr, one deadline."""
_EXECUTED_CODE = __import__('sys')._getframe().f_code
import os
import selectors
import signal
import subprocess
import sys
import time
from .serialization import encode, decode, EvidenceError, CONTROL_LIMIT
from .contracts import require


def call(request, budget):
    budget.tick()
    raw = encode(request)
    deadline = min(budget.deadline, time.monotonic() + 2)
    process = subprocess.Popen([sys.executable, '-I', '-B', '-m', 'agent_evidence._worker'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={'LC_ALL':'C','LANG':'C'}, cwd='/', start_new_session=True, close_fds=True)
    output = bytearray(); errors = bytearray(); offset = 0
    selector = selectors.DefaultSelector()
    try:
        for stream, event, tag in ((process.stdin,selectors.EVENT_WRITE,'in'),
                                   (process.stdout,selectors.EVENT_READ,'out'),
                                   (process.stderr,selectors.EVENT_READ,'err')):
            os.set_blocking(stream.fileno(), False); selector.register(stream,event,tag)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'worker_timeout')
            for key, _ in selector.select(remaining):
                stream = key.fileobj
                if key.data == 'in':
                    try:
                        offset += os.write(stream.fileno(), raw[offset:offset+16384])
                    except BrokenPipeError:
                        raise EvidenceError('worker_protocol') from None
                    if offset == len(raw):
                        selector.unregister(stream); stream.close()
                else:
                    chunk = os.read(stream.fileno(), 16384)
                    if not chunk:
                        selector.unregister(stream); stream.close(); continue
                    sink = output if key.data == 'out' else errors
                    sink.extend(chunk)
                    require(len(sink) <= (CONTROL_LIMIT if key.data == 'out' else 16384), 'worker_output_limit')
        remaining = deadline - time.monotonic()
        require(remaining > 0, 'worker_timeout')
        try:
            code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            raise EvidenceError('worker_timeout') from None
        require(code == 0 and not errors, 'worker_protocol')
        result = decode(bytes(output))
        require(type(result.get('bytes_read')) is int, 'worker_protocol')
        budget.charge(result['bytes_read'])
        return result
    except BaseException:
        # Unknown consumption is not reusable by a subsequent system.
        budget.left = 0
        raise
    finally:
        selector.close()
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        for stream in (process.stdin,process.stdout,process.stderr):
            stream.close()
