"""POSIX descriptor anchoring, stable reads and exclusive publications."""
_EXECUTED_CODE = __import__('sys')._getframe().f_code
import hashlib
import os
import stat
import uuid
from contextlib import contextmanager
from .contracts import member, require
from .serialization import EvidenceError, CONTROL_LIMIT, REPORT_LIMIT


def supported():
    require(os.name == 'posix' and all(hasattr(os, k) for k in ('O_NOFOLLOW','O_DIRECTORY','O_NONBLOCK')), 'unsupported_platform')


def absolute(path):
    require(isinstance(path, str) and path.startswith('/') and len(path) <= 4096, 'boundary_invalid')
    require(path == '/' or all(p not in ('', '.', '..') for p in path[1:].split('/')), 'boundary_invalid')
    return path


def _check_anchors(anchors):
    for parent, name, child in anchors:
        actual = os.stat(name, dir_fd=parent, follow_symlinks=False)
        expected = os.fstat(child)
        require((actual.st_dev, actual.st_ino) == (expected.st_dev, expected.st_ino)
                and stat.S_ISDIR(actual.st_mode), 'boundary_invalid')


@contextmanager
def directory(path):
    supported(); absolute(path)
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    anchors = []
    try:
        for part in path.split('/')[1:]:
            if not part:
                continue
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            anchors.append((fd, part, nxt)); fd = nxt
        yield fd
        _check_anchors(anchors)
    finally:
        os.close(fd)
        for parent, _, _ in reversed(anchors):
            os.close(parent)


def identity(fd):
    value = os.fstat(fd)
    return hashlib.sha256(f'{value.st_dev}:{value.st_ino}'.encode()).hexdigest()


def bound(path, fd):
    """Reopen the lexical root without following links at a consumption boundary."""
    with directory(path) as current:
        require(identity(current) == identity(fd), 'boundary_invalid')


@contextmanager
def leaf(root_fd, path):
    member(path)
    fd = os.dup(root_fd)
    anchors = []
    try:
        parts = path.split('/')
        for part in parts[:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            anchors.append((fd, part, nxt)); fd = nxt
        target = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            before = os.fstat(target)
            require(stat.S_ISREG(before.st_mode), 'target_not_regular')
            require(before.st_nlink == 1, 'hardlink_denied')
            yield target
            _check_anchors(anchors)
            after = os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
            require((before.st_dev,before.st_ino) == (after.st_dev,after.st_ino), 'target_drift')
        finally:
            os.close(target)
    finally:
        os.close(fd)
        for parent, _, _ in reversed(anchors):
            os.close(parent)


def read(root_fd, path, budget, limit=1048576):
    budget.tick()
    with leaf(root_fd, path) as fd:
        before = os.fstat(fd)
        require(before.st_size <= limit, 'target_too_large')
        require(before.st_size < budget.left, 'budget_exhausted')
        data = bytearray()
        while True:
            budget.tick()
            chunk = os.read(fd, min(65536, limit + 1 - len(data), budget.left))
            if not chunk:
                break
            budget.charge(len(chunk)); data.extend(chunk)
            require(len(data) <= limit, 'target_too_large')
        after = os.fstat(fd)
        require(all(getattr(before,k) == getattr(after,k) for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')), 'target_drift')
        require(len(data) == before.st_size, 'target_drift')
        return bytes(data)


def publish(root_fd, name, data):
    limit = REPORT_LIMIT if name == 'report.json' else CONTROL_LIMIT
    member(name); require('/' not in name and isinstance(data, bytes) and len(data) <= limit)
    temp = 'pending-' + uuid.uuid4().hex
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=root_fd)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        # link is exclusive: a loser never deletes or replaces a winner.
        os.link(temp, name, src_dir_fd=root_fd, dst_dir_fd=root_fd, follow_symlinks=False)
        os.fsync(root_fd)
    finally:
        os.unlink(temp, dir_fd=root_fd)
    # Output-only bounded readback is not input acquisition and cannot renew its
    # exhausted budget. Preserve failure reports even after acquisition timeout.
    with leaf(root_fd, name) as check:
        require(os.fstat(check).st_size == len(data), 'receipt_drift')
        observed = bytearray()
        while len(observed) <= len(data):
            chunk = os.read(check, min(65536, len(data) + 1 - len(observed)))
            if not chunk:
                break
            observed.extend(chunk)
        require(bytes(observed) == data, 'receipt_drift')


def new_directory(path):
    absolute(path)
    parent, _, name = path.rpartition('/')
    require(bool(name), 'boundary_invalid')
    member(name)
    with directory(parent or '/') as fd:
        os.mkdir(name, mode=0o700, dir_fd=fd)
        os.fsync(fd)
