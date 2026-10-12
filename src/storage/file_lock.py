"""Short cross-process config lock; process death releases the OS lock."""
from contextlib import contextmanager
from pathlib import Path
import os
import time

@contextmanager
def file_lock(path,timeout=5):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with open(path,'a+b') as stream:
        if stream.tell()==0:stream.write(b'0');stream.flush()
        end=time.monotonic()+timeout
        while True:
            try:
                stream.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic()>=end:raise ValueError('QUERY_VERSION_CONFLICT') from None
                time.sleep(.05)
        try:yield
        finally:
            stream.seek(0)
            if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
