# autopep8'd
import os
from pyVmomi import vmodl
import re


def serialize(*arg, **kwarg):
    """
        Serialize into the format
        item1:item2:key1=value1:key2:value2
    """
    escape_dict = {'\\': '\\\\', '\n': '\\n', '\r': '\\r', ',': '\\,', ':': '\\:', '=': '\\='}
    pattern = re.compile("|".join([re.escape(k) for k in sorted(escape_dict, key=len, reverse=True)]), flags=re.DOTALL)
    items = []
    for item in arg:
        items.append(pattern.sub(lambda x: escape_dict[x.group(0)], str(item)))
    for k, v in kwarg.items():
        items.append("{}={}".format(
            pattern.sub(lambda x: escape_dict[x.group(0)], str(k)),
            pattern.sub(lambda x: escape_dict[x.group(0)], str(v))
        ))
    return ':'.join(items)


def deserialize(s):
    """
        Deserialize the format into a list and dict
        item1:item2:key1=value1:key2:value2
    """
    escape_dict = {'\\r': '\r', '\\\\': '\\', '\\=': '=', '\\:': ':', '\\n': '\n', '\\,': ','}
    pattern = re.compile("|".join([re.escape(k) for k in sorted(escape_dict, key=len, reverse=True)]), flags=re.DOTALL)
    arg = []
    kwarg = {}
    for name, eq, value in re.findall(r'((?:\\.|[^=:\\]+)+)(?:(=)((?:\\.|[^:\\]+)+))?', s):
        if eq:
            kwarg[pattern.sub(lambda x: escape_dict[x.group(0)], name)] = pattern.sub(
                lambda x: escape_dict[x.group(0)], value)
        else:
            arg.append(pattern.sub(lambda x: escape_dict[x.group(0)], name))
    return (arg, kwarg)


class TriggeredAlarm(object):
    def __init__(self, name, status):
        self.name = name
        self.sensorStatus = status

    def __str__(self):
        return serialize('triggeredAlarm', self.name, self.sensorStatus)


class NumericSensorInfo(object):
    def __init__(self, name, status, type="n/a", value="n/a", unitModifier="n/a", unit="n/a"):
        self.name = name
        self.type = type
        self.sensorStatus = status
        self.value = value
        self.unitModifier = unitModifier
        self.unit = unit

    def __str__(self):
        return serialize('numericSensorInfo', name=self.name, type=self.type, sensorStatus=self.sensorStatus, value=self.value, unitModifier=self.unitModifier, unit=self.unit)


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
                (f.key, f.name)
                for f in content.customFieldsManager.field
                if f.managedObjectType in (obj_type, None)
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
                    properties[prop.name] = [
                        TriggeredAlarm(
                            name=item.alarm.info.systemName.split('.')[1],
                            status=item.overallStatus
                        ) for item in prop.val
                    ]
                except Exception:
                    properties[prop.name] = [
                        TriggeredAlarm(
                            name='AlarmsUnavailable',
                            status='yellow'
                        )
                    ]

            elif 'runtime.healthSystemRuntime.systemHealthInfo.numericSensorInfo' == prop.name:
                """
                    handle numericSensorInfo
                """

                properties[prop.name] = [
                    NumericSensorInfo(
                        name=item.name,
                        type=item.sensorType,
                        status=item.healthState.key,
                        value=item.currentReading,
                        unitModifier=item.unitModifier,
                        unit=item.baseUnits.lower()
                    ) for item in prop.val
                ]

            elif prop.name in [
                'runtime.healthSystemRuntime.hardwareStatusInfo.cpuStatusInfo',
                'runtime.healthSystemRuntime.hardwareStatusInfo.memoryStatusInfo',
            ]:
                """
                    handle hardwareStatusInfo
                """

                properties[prop.name] = [
                    NumericSensorInfo(
                        name=item.name,
                        status=item.status.key
                    ) for item in prop.val
                ]

            else:
                properties[prop.name] = prop.val

        results[obj.obj._moId] = properties

    return results
