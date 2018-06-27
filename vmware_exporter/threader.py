import threading


class Threader(object):
    """
    Takes method and data and threads it
    """
    _thread = ''

    def thread_it(self, method, data):
        """
        Thread any method and data will be used as args
        """
        self._thread = threading.Thread(target=method, args=(data))
        self._thread.start()
        if threading.active_count() >= 50:
            self.join()

    def join(self):
        """
        join all threads and complete them
        """
        try:
            self._thread.join()
        except RuntimeError:
            # Thread terminated.
            pass
        except ReferenceError:
            pass
