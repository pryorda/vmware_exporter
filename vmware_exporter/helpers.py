# autopep8'd
import os
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

    """
        Gathering all custom attibutes names are stored as key (integer) in CustomFieldsManager
        We do not want those keys, but the names. So here the names and keys are gathered to
        be translated later
    """
    if ('customValue' in properties) or ('summary.customValue' in properties):

        allCustomAttributesNames = {}

        if content.customFieldsManager and content.customFieldsManager.field:
            allCustomAttributesNames.update(
                dict(
                    [
                        (f.key, f.name)
                        for f in content.customFieldsManager.field
                        if f.managedObjectType in (obj_type, None)
                    ]
                )
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

            """
                if it's a custom value property for vms (summary.customValue), hosts (summary.customValue)
                or datastores (customValue) - we store all attributes together in a python dict and
                translate its name key to name
            """
            if 'customValue' in prop.name:

                properties[prop.name] = {}

                if allCustomAttributesNames:

                    properties[prop.name] = dict(
                        [
                            (allCustomAttributesNames[attribute.key], attribute.value)
                            for attribute in prop.val
                            if attribute.key in allCustomAttributesNames
                        ]
                    )

            elif 'triggeredAlarmState' == prop.name:
                """
                    triggered alarms
                """
                try:
                    alarms = list(
                        'triggeredAlarm:{}:{}'.format(item.alarm.info.systemName.split('.')[1], item.overallStatus)
                        for item in prop.val
                    )
                except Exception:
                    alarms = ['triggeredAlarm:AlarmsUnavailable:yellow']

                properties[prop.name] = ','.join(alarms)

            elif 'runtime.healthSystemRuntime.systemHealthInfo.numericSensorInfo' == prop.name:
                """
                    handle numericSensorInfo
                """
                sensors = list(
                    'numericSensorInfo:name={}:type={}:sensorStatus={}:value={}:unitModifier={}:unit={}'.format(
                        item.name,
                        item.sensorType,
                        item.healthState.key,
                        item.currentReading,
                        item.unitModifier,
                        item.baseUnits.lower()
                    )
                    for item in prop.val
                )
                properties[prop.name] = ','.join(sensors)

            elif prop.name in [
                'runtime.healthSystemRuntime.hardwareStatusInfo.cpuStatusInfo',
                'runtime.healthSystemRuntime.hardwareStatusInfo.memoryStatusInfo',
            ]:
                """
                    handle hardwareStatusInfo
                """
                sensors = list(
                    'numericSensorInfo:name={}:type={}:sensorStatus={}:value={}:unitModifier={}:unit={}'.format(
                        item.name,
                        "n/a",
                        item.status.key,
                        "n/a",
                        "n/a",
                        "n/a",
                    )
                    for item in prop.val
                )
                properties[prop.name] = ','.join(sensors)

            else:
                properties[prop.name] = prop.val

        results[obj.obj._moId] = properties

    return results
