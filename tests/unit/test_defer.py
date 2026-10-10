import pytest_twisted
from twisted.internet import defer
from twisted.python import failure

from vmware_exporter.defer import BranchingDeferred, parallelize, run_once_property


@pytest_twisted.inlineCallbacks
def test_parallel_branches_both_receive_result():
    '''
    Two coroutines blocking on the same BranchingDeferred must both be resumed.

    This is the pattern run_once_property relies on, and the one that broke on
    Twisted 24.10: addBoth started appending Twisted's own callback tuple onto
    the internal callback list, which callback() then tried to fire as if it
    were a Deferred.
    '''
    branching = BranchingDeferred()

    @defer.inlineCallbacks
    def consumer(name):
        value = yield branching
        return '{0}:{1}'.format(name, value)

    first = consumer('first')
    second = consumer('second')

    branching.callback('content')

    results = yield parallelize(first, second)
    assert results == ('first:content', 'second:content')


@pytest_twisted.inlineCallbacks
def test_branch_added_after_result_is_available():
    branching = BranchingDeferred()
    branching.callback('content')

    value = yield branching
    assert value == 'content'


@pytest_twisted.inlineCallbacks
def test_errback_reaches_every_branch():
    branching = BranchingDeferred()

    @defer.inlineCallbacks
    def consumer():
        try:
            yield branching
        except ValueError as exc:
            return str(exc)
        raise AssertionError('the failure did not reach the branch')

    first = consumer()
    second = consumer()

    branching.errback(failure.Failure(ValueError('boom')))

    results = yield parallelize(first, second)
    assert results == ('boom', 'boom')


@pytest_twisted.inlineCallbacks
def test_run_once_property_runs_once_and_feeds_every_consumer():
    calls = []

    class Collector(object):

        @run_once_property
        @defer.inlineCallbacks
        def content(self):
            calls.append(1)
            yield defer.succeed(None)
            return 'content'

        @defer.inlineCallbacks
        def branch(self):
            value = yield self.content
            return value

    collector = Collector()
    results = yield parallelize(collector.branch(), collector.branch())

    assert results == ('content', 'content')
    assert len(calls) == 1
