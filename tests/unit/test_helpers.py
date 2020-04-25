import os

from unittest import mock

from pyVmomi import vim

from vmware_exporter.helpers import batch_fetch_properties, get_bool_env


class FakeView(vim.ManagedObject):

    def __init__(self):
        super().__init__('dummy-moid')

    def Destroy(self):
        pass


def test_get_bool_env():
    # Expected behaviour
    assert get_bool_env('NON_EXISTENT_ENV', True)

    # #102 'bool("False") will evaluate to True in Python'
    os.environ['VSPHERE_COLLECT_VMS'] = "False"
    assert not get_bool_env('VSPHERE_COLLECT_VMS', True)

    # Environment is higher prio than defaults
    os.environ['ENVHIGHERPRIO'] = "True"
    assert get_bool_env('ENVHIGHERPRIO', False)
    assert get_bool_env('ENVHIGHERPRIO', True)

    os.environ['ENVHIGHERPRIO_F'] = "False"
    assert not get_bool_env('ENVHIGHERPRIO_F', False)
    assert not get_bool_env('ENVHIGHERPRIO_F', True)

    # Accent upper and lower case in env vars
    os.environ['ENVHIGHERPRIO_F'] = "false"
    assert not get_bool_env('ENVHIGHERPRIO_F', True)


def test_batch_fetch_properties():
    content = mock.Mock()

    # There is strict parameter checking - this must be a ManagedObject, not a mock,
    # but the real return value has methods with side effects. So we need to use a fake.
    content.viewManager.CreateContainerView.return_value = FakeView()

    mockCustomField1 = mock.Mock()
    mockCustomField1.key = 1
    mockCustomField1.name = 'customAttribute1'
    mockCustomField1.managedObjectType = vim.Datastore

    mockCustomField2 = mock.Mock()
    mockCustomField2.key = 2
    mockCustomField2.name = 'customAttribute2'
    mockCustomField1.managedObjectType = vim.VirtualMachine

    content.customFieldsManager.field = [
        mockCustomField1,
        mockCustomField2,
    ]

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
