"""Detached tool entrypoint with an inherited supervisor lifetime capability."""
import os
import runpy
import signal
import threading


def main():
    descriptor = os.environ.get('MINI_NOTA_LIFETIME_FD')
    if descriptor:
        fd = int(descriptor)
        # Never continue work if the lifetime descriptor was not inherited.
        os.fstat(fd)
        def watch():
            while os.read(fd, 1):
                pass
            os.killpg(os.getpgrp(), signal.SIGKILL)
        threading.Thread(target=watch, daemon=True).start()
    runpy.run_module(os.environ.get('ENGINE_WORKER_MODULE','service.engine_worker'),run_name='__main__')


if __name__ == '__main__':
    main()
