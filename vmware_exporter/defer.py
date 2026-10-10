'''
Helpers for writing efficient twisted code, optimized for coroutine scheduling efficiency
'''
# autopep8'd

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

    This implementation deliberately keeps its own state under private names and
    never writes to the attributes Twisted uses internally. Older Twisted
    versions routed every `addCallback`/`addErrback`/`addBoth` through
    `addCallbacks`, so overriding that one method was enough. Since Twisted
    24.10 `addBoth` appends its own callback tuple straight onto the internal
    list, and in 25.x that list moved to `_callbacks` and `callbacks` became a
    read-only deprecated property. So every `add*` entry point is overridden
    here to hand out an ordinary Deferred branch instead.
    '''

    def __init__(self):
        super().__init__()
        self._branches = []
        self.result = None

    def _branch(self):
        ''' An ordinary Deferred that fires when this one does. '''
        if self.result is None:
            d = defer.Deferred()
            self._branches.append(d)
            return d

        if isinstance(self.result, failure.Failure):
            return defer.fail(self.result)

        return defer.succeed(self.result)

    def callback(self, result):
        self.result = result
        while self._branches:
            self._branches.pop(0).callback(result)

    def errback(self, err):
        self.result = err
        while self._branches:
            self._branches.pop(0).errback(err)

    def addCallbacks(self, *args, **kwargs):
        return self._branch().addCallbacks(*args, **kwargs)

    def addCallback(self, *args, **kwargs):
        return self._branch().addCallback(*args, **kwargs)

    def addErrback(self, *args, **kwargs):
        return self._branch().addErrback(*args, **kwargs)

    def addBoth(self, *args, **kwargs):
        return self._branch().addBoth(*args, **kwargs)


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
