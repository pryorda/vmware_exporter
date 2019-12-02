import os
from datetime import datetime, timedelta
from pyVmomi import vmodl


def get_bool_env(key: str, default: bool):
    value = os.environ.get(key, default)
    return value if type(value) == bool else value.lower() == 'true'


def batch_fetch_properties(content, obj_type, properties):
    view_ref = content.viewManager.CreateContainerView(
        container=content.rootFolder,
        type=[obj_type],
        recursive=True
    )

    try:
        PropertyCollector = vmodl.query.PropertyCollector

        # Describe the list of properties we want to fetch for obj_type
        property_spec = PropertyCollector.PropertySpec()
        property_spec.type = obj_type
        property_spec.pathSet = properties

        # Describe where we want to look for obj_type
        traversal_spec = PropertyCollector.TraversalSpec()
        traversal_spec.name = 'traverseEntities'
        traversal_spec.path = 'view'
        traversal_spec.skip = False
        traversal_spec.type = view_ref.__class__

        obj_spec = PropertyCollector.ObjectSpec()
        obj_spec.obj = view_ref
        obj_spec.skip = True
        obj_spec.selectSet = [traversal_spec]

        filter_spec = PropertyCollector.FilterSpec()
        filter_spec.objectSet = [obj_spec]
        filter_spec.propSet = [property_spec]

        props = content.propertyCollector.RetrieveContents([filter_spec])
    finally:
        view_ref.Destroy()

    results = {}
    for obj in props:
        properties = {}
        properties['obj'] = obj.obj
        properties['id'] = obj.obj._moId

        for prop in obj.propSet:
            properties[prop.name] = prop.val

        results[obj.obj._moId] = properties

    return results


def batch_fetch_events(content, event_type, scrape_duration):
    event_mgr = content.eventManager
    list_events = event_mgr.description.eventInfo
    ha_events = get_all_ha_events(event_type, list_events)
    now = datetime.now()
    time_filter = event_type.EventFilterSpec.ByTime()
    time_filter.beginTime = now - timedelta(seconds=scrape_duration)
    time_filter.endTime = now
    filter_spec = event_type.EventFilterSpec(eventTypeId=ha_events, time=time_filter)
    results = []
    try:
        event_collector = event_mgr.CreateCollectorForEvents(filter=filter_spec)
        for event in event_collector.ReadNextEvents(maxCount=1000):
            properties = {}
            timestamp = datetime.timestamp(event.createdTime)
            properties['obj'] = str(event.key) + str(timestamp)
            properties['dc_name'] = getattr(getattr(event, 'datacenter', ''), 'name', '')
            properties['cluster_name'] = getattr(getattr(event, 'computeResource', ''), 'name', '')
            properties['host_name'] = getattr(getattr(event, 'host', ''), 'name', '')
            properties['vm_name'] = getattr(getattr(event, 'vm', ''), 'name', '')
            properties['user_name'] = getattr(event, 'userName', '')
            properties['event'] = str(getattr(event, 'eventTypeId', ''))
            properties['message'] = getattr(event, 'fullFormattedMessage', '')
            results.append(properties)
    finally:
        event_collector.DestroyCollector()
    return results

def get_all_ha_events(event_type, list_events):
    filtered_events = [event_info for event_info in list_events if 
                       event_info.key == event_type.ExtendedEvent or event_info.key == event_type.EventEx]
    ha_events = [event_info.fullFormat.split('|')[0] for event_info in filtered_events if 
                 (event_info.category == "error" or event_info.category == "warning") and (
                     "com.vmware.vc.ha" in event_info.fullFormat.split('|')[0] or 'com.vmware.vc.HA' in 
                 event_info.fullFormat.split('|')[0])]
    return ha_events