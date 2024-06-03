import signal


class GracefulInterruptHandler(object):
    """
    Borrowed from https://gist.github.com/nonZero/2907502
    """
    def __init__(self, signals=(signal.SIGINT, signal.SIGTERM), on_interrupt=None):
        self.signals = signals
        self.original_handlers = {}
        self.interrupted = False
        self.on_interrupt = on_interrupt

    def __enter__(self):
        self.interrupted = False
        self.released = False

        for sig in self.signals:
            self.original_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, self.handler)

        return self

    def handler(self, signum, frame):
        self.release()
        self.interrupted = True
        if callable(self.on_interrupt):
            self.on_interrupt(signum)

    def __exit__(self, type, value, tb):
        self.release()

    def release(self):
        if self.released:
            return False

        for sig in self.signals:
            signal.signal(sig, self.original_handlers[sig])

        self.released = True
        return True
