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


def batch_fetch_events(content, event_type, properties):
    time_filter = event_type.EventFilterSpec.ByTime()
    event_mgr = content.eventManager
    now = datetime.now()
    time_filter.beginTime = now - timedelta(minutes=120)
    time_filter.endTime = now
    filter_spec = event_type.EventFilterSpec(eventTypeId=properties, time=time_filter)
    event_collector = event_mgr.CreateCollectorForEvents(filter=filter_spec)
    results = []
    for event in event_collector.ReadNextEvents(maxCount=1000):
        if hasattr(event, 'eventTypeId'):
            properties = {}
            timestamp = datetime.timestamp(event.createdTime)
            properties['obj'] = str(event.eventTypeId) + str(timestamp)
            properties['timestamp'] = timestamp
            if getattr(event,'userName'):
                properties['user_name'] = event.userName
            else:
                properties['user_name'] = ''
            if getattr(event,'vm'):
                properties['vm_name'] = event.vm
            else:
                properties['vm_name'] = ''
            if getattr(event,'datacenter'):
                properties['dc_name'] = event.datacenter.name
            else:
                properties['dc_name'] = ''
            if getattr(event,'computeResource'):
                properties['host_name'] = event.computeResource.name
            else:
                properties['host_name'] = ''
            if getattr(event,'fullFormattedMessage'):
                properties['message'] = event.fullFormattedMessage
            else:
                properties['message'] = ''
            if getattr(event,'eventTypeId'):
                properties['event'] = event.eventTypeId
            else:
                properties['event'] = event.reason
            results.append(properties)
    print('TTTTTT')
    print(results)
    return results