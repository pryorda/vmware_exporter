import os

from unittest import mock

from pyVmomi import vim

from vmware_exporter.helpers import batch_fetch_properties, get_bool_env


class FakeView(vim.ManagedObject):

    def __init__(self):
        super().__init__('dummy-moid')

    def Destroy(self):
        pass

class FakeEventDetail():

    def __init__(self):
        self.key = vim.event.ExtendedEvent
        self.description = 'vSphere HA failed to restart a network isolated virtual machine',
        self.category = 'error',
        self.fullFormat = 'com.vmware.vc.HA.FailedRestartAfterIsolationEvent|vSphere HA was unable to restart virtual machine vm1 in cluster cluster1 in datacenter datacenter1 after it was powered off in response to a network isolation event. The virtual machine should be manually powered back on.',


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


def test_batch_fetch_events(content, event_type, scrape_duration):
    pass
    # event_mgr = mock.Mock()
    


    # event_mgr.description.eventInfo.return_value = [FakeEventDetail()]
    # ha_events = get_all_ha_events(event_type, list_events)
    # now = datetime.now()
    # time_filter = event_type.EventFilterSpec.ByTime()
    # time_filter.beginTime = now - timedelta(seconds=scrape_duration)
    # time_filter.endTime = now
    # filter_spec = event_type.EventFilterSpec(eventTypeId=ha_events, time=time_filter)
    # results = []
    # try:
    #     event_collector = event_mgr.CreateCollectorForEvents(filter=filter_spec)
    #     for event in event_collector.ReadNextEvents(maxCount=1000):
    #         properties = {}
    #         timestamp = datetime.timestamp(event.createdTime)
    #         properties['obj'] = str(event.key) + str(timestamp)
    #         properties['dc_name'] = getattr(getattr(event, 'datacenter', ''), 'name', '')
    #         properties['cluster_name'] = getattr(getattr(event, 'computeResource', ''), 'name', '')
    #         properties['host_name'] = getattr(getattr(event, 'host', ''), 'name', '')
    #         properties['vm_name'] = getattr(getattr(event, 'vm', ''), 'name', '')
    #         properties['user_name'] = getattr(event, 'userName', '')
    #         properties['event'] = str(getattr(event, 'eventTypeId', ''))
    #         properties['message'] = getattr(event, 'fullFormattedMessage', '')
    #         results.append(properties)
    # finally:
    #     event_collector.DestroyCollector()
    # return results

def get_all_ha_events(event_type, list_events):
    pass
    # filtered_events = [event_info for event_info in list_events if 
    #                    event_info.key == event_type.ExtendedEvent or event_info.key == event_type.EventEx]
    # ha_events = [event_info.fullFormat.split('|')[0] for event_info in filtered_events if 
    #              (event_info.category == "error" or event_info.category == "warning") and (
    #                  "com.vmware.vc.ha" in event_info.fullFormat.split('|')[0] or 'com.vmware.vc.HA' in 
    #              event_info.fullFormat.split('|')[0])]
    # return ha_events