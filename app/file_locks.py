"""Cross-platform, process-scoped file locks using only the standard library."""
import contextlib,os,pathlib,time
@contextlib.contextmanager
def lock_path(path,blocking=True):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    f=path.open('a+b');held=False
    try:
        if os.name=='nt':
            import msvcrt
            if path.stat().st_size==0:f.write(b'0');f.flush()
            while True:
                try:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1);held=True;break
                except OSError:
                    if not blocking:raise BlockingIOError('Task lock is already held') from None
                    time.sleep(.1)
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX|(0 if blocking else fcntl.LOCK_NB));held=True
        yield
    finally:
        if held:
            if os.name=='nt':
                import msvcrt
                f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(f,fcntl.LOCK_UN)
        f.close()
