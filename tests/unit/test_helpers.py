import os

from unittest import mock

from pyVmomi import vim

from vmware_exporter.helpers import batch_fetch_properties, get_bool_env


class FakeView(vim.ManagedObject):

    def __init__(self):
        super().__init__('dummy-moid')

    def Destroy(self):
        pass


def test_get_bool_env_with_default_value():
    value = get_bool_env('INEXISTENT_ENV', True)

    assert value == True

def test_get_bool_env_with_a_valid_env():
    key = "TEST_BOOLEAN_VALUE"

    os.environ[key] = "True"

    value = get_bool_env(key, False)

    assert value == True

def test_batch_fetch_properties():
    content = mock.Mock()

    # There is strict parameter checking - this must be a ManagedObject, not a mock,
    # but the real return value has methods with side effects. So we need to use a fake.
    content.viewManager.CreateContainerView.return_value = FakeView()

    prop1 = mock.Mock()
    prop1.name = 'someprop'
    prop1.val = 1

    prop2 = mock.Mock()
    prop2.name = 'someotherprop'
    prop2.val = 2

    mock_props = mock.Mock()
    mock_props.obj._moId = 'vm:1'
    mock_props.propSet = [prop1, prop2]

    content.propertyCollector.RetrieveContents.return_value = [mock_props]

    results = batch_fetch_properties(
        content,
        vim.Datastore,
        ['someprop', 'someotherprop'],
    )

    assert results == {
        'vm:1': {
            'obj': mock_props.obj,
            'id': 'vm:1',
            'someprop': 1,
            'someotherprop': 2,
        }
    }
