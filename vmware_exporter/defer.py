'''
Helpers for writing efficient twisted code, optimized for coroutine scheduling efficiency
'''

from twisted.internet import defer
from twisted.python import failure


class BranchingDeferred(defer.Deferred):

    '''
    This is meant for code where you are doing something like this:

    content = yield self.get_connection_content()
    results = yield defer.DeferredList([
        self.get_hosts(content),
        self.get_datastores(content),
    ])

    This allows get_hosts and get_datastores to run in parallel, which is good.
    But what if you don't want the whole of get_hosts to wait for
    get_connection_content() to be complete?

    We have a bunch of places where it would be better for scheduling if we did this:

    content = self.get_connection_content()
    results = yield defer.DeferredList([
        self.get_hosts(content),
        self.get_datastores(content),
    ])

    Now we don't have to wait for content to be finished before get_hosts etc
    starts running. It is up to get_hosts to block on the content deferred itself.

    (Thats a contrived example, the real win is allowing host_labels and
    vm_inventory to run in parallel).

    Unfortunately you can't have parallel branches blocking on the same deferred
    like this with a standard Twisted deferred.

    This is a deferred that enables the parallel branching use case.
    '''

    def __init__(self):
        self.callbacks = []
        self.result = None

    def callback(self, result):
        self.result = result
        while self.callbacks:
            self.callbacks.pop(0).callback(result)

    def errback(self, err):
        self.result = err
        while self.callbacks:
            self.callbacks.pop(0).errback(err)

    def addCallbacks(self, *args, **kwargs):
        if not self.result:
            d = defer.Deferred()
            d.addCallbacks(*args, **kwargs)
            self.callbacks.append(d)
            return

        if isinstance(self.result, failure.Failure):
            defer.fail(self.result).addCallbacks(*args, **kwargs)
            return

        defer.succeed(self.result).addCallbacks(*args, **kwargs)


class run_once_property(object):

    '''
    This is a property descriptor that caches the first result it retrieves. It
    does this by setting keys in self.__dict__ on the parent class instance.
    This is fast - python won't even bother running our descriptor next time
    because attributes in self.__dict__ on a class instance trump descriptors
    on the class.

    This is intended to be used with the Collector class which has a request
    bound lifecycle (this isn't going to cache stuff forever and cause memory
    leaks).
    '''

    def __init__(self, callable):
        self.callable = callable

    def __get__(self, obj, cls):
        if obj is None:
            return self
        result = obj.__dict__[self.callable.__name__] = BranchingDeferred()
        self.callable(obj).chainDeferred(result)
        return result


@defer.inlineCallbacks
def parallelize(*args):
    results = yield defer.DeferredList(args, fireOnOneErrback=True)
    return tuple(r[1] for r in results)
