from concurrent.futures import ThreadPoolExecutor

THREAD_LIMIT = 25


class Threader(object):

    def __init__(self):
        self._workers = ThreadPoolExecutor(max_workers=THREAD_LIMIT)

    def thread_it(self, method, data):
        self._workers.submit(method, *data)

    def join(self):
        self._workers.shutdown(wait=True)
