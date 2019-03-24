import contextlib
import datetime
from unittest import mock

import pytest
import pytest_twisted
import pytz
from pyVmomi import vim, vmodl
from twisted.internet import defer
from twisted.web.server import NOT_DONE_YET

from vmware_exporter.vmware_exporter import main, HealthzResource, VmwareCollector, VMWareMetricsResource
from vmware_exporter.defer import BranchingDeferred


EPOCH = datetime.datetime(1970, 1, 1, tzinfo=pytz.utc)


def _check_properties(properties):
    ''' This will run the prop list through the pyvmomi serializer and catch malformed types (not values) '''
    PropertyCollector = vmodl.query.PropertyCollector
    property_spec = PropertyCollector.PropertySpec()
    property_spec.pathSet = properties
    return len(property_spec.pathSet) > 0


def _succeed(result):
    d = BranchingDeferred()
    defer.succeed(result).chainDeferred(d)
    return d


@pytest_twisted.inlineCallbacks
def test_collect_vms():
    boot_time = EPOCH + datetime.timedelta(seconds=60)

    snapshot_1 = mock.Mock()
    snapshot_1.createTime = EPOCH + datetime.timedelta(seconds=60)
    snapshot_1.name = 'snapshot_1'
    snapshot_1.childSnapshotList = []

    snapshot_2 = mock.Mock()
    snapshot_2.createTime = EPOCH + datetime.timedelta(seconds=120)
    snapshot_2.name = 'snapshot_2'
    snapshot_2.childSnapshotList = [snapshot_1]

    snapshot = mock.Mock()
    snapshot.rootSnapshotList = [snapshot_2]

    disk = mock.Mock()
    disk.diskPath = '/boot'
    disk.capacity = 100
    disk.freeSpace = 50

    collect_only = {
        'vms': True,
        'vmguests': True,
        'datastores': True,
        'hosts': True,
        'snapshots': True,
    }
    collector = VmwareCollector(
        '127.0.0.1',
        'root',
        'password',
        collect_only,
    )
    collector.content = _succeed(mock.Mock())

    collector.__dict__['vm_labels'] = _succeed({
        'vm-1': ['vm-1', 'host-1', 'dc', 'cluster-1'],
        'vm-2': ['vm-2', 'host-1', 'dc', 'cluster-1'],
        'vm-3': ['vm-3', 'host-1', 'dc', 'cluster-1'],
    })

    metrics = collector._create_metric_containers()

    with mock.patch.object(collector, 'batch_fetch_properties') as batch_fetch_properties:
        batch_fetch_properties.return_value = _succeed({
            'vm-1': {
                'name': 'vm-1',
                'runtime.host': vim.ManagedObject('host-1'),
                'runtime.powerState': 'poweredOn',
                'summary.config.numCpu': 1,
                'summary.config.memorySizeMB': 1024,
                'runtime.bootTime': boot_time,
                'snapshot': snapshot,
                'guest.disk': [disk],
                'guest.toolsStatus': 'toolsOk',
                'guest.toolsVersion': '10336',
                'guest.toolsVersionStatus2': 'guestToolsUnmanaged',
            },
            'vm-2': {
                'name': 'vm-2',
                'runtime.powerState': 'poweredOff',
                'summary.config.numCpu': 1,
                'summary.config.memorySizeMB': 1024,
                'runtime.bootTime': boot_time,
                'snapshot': snapshot,
                'guest.disk': [disk],
                'guest.toolsStatus': 'toolsOk',
                'guest.toolsVersion': '10336',
                'guest.toolsVersionStatus2': 'guestToolsUnmanaged',
            },
            'vm-3': {
                'name': 'vm-3',
                'runtime.host': vim.ManagedObject('host-1'),
                'runtime.powerState': 'poweredOff',
                'summary.config.numCpu': 1,
                'summary.config.memorySizeMB': 1024,
                'runtime.bootTime': boot_time,
                'snapshot': snapshot,
                'guest.disk': [disk],
                'guest.toolsStatus': 'toolsOk',
                'guest.toolsVersion': '10336',
                'guest.toolsVersionStatus2': 'guestToolsUnmanaged',
            },
        })
        yield collector._vmware_get_vms(metrics)
        assert _check_properties(batch_fetch_properties.call_args[0][1])

    # Assert that vm-3 skipped #69/#70
    assert metrics['vmware_vm_power_state'].samples[1][1] == {
        'vm_name': 'vm-3',
        'host_name': 'host-1',
        'cluster_name': 'cluster-1',
        'dc_name': 'dc',
    }

    # General VM metrics
    assert metrics['vmware_vm_power_state'].samples[0][1] == {
        'vm_name': 'vm-1',
        'host_name': 'host-1',
        'cluster_name': 'cluster-1',
        'dc_name': 'dc',
    }
    assert metrics['vmware_vm_power_state'].samples[0][2] == 1.0

    assert metrics['vmware_vm_boot_timestamp_seconds'].samples[0][1] == {
        'vm_name': 'vm-1',
        'host_name': 'host-1',
        'cluster_name': 'cluster-1',
        'dc_name': 'dc',
    }
    assert metrics['vmware_vm_boot_timestamp_seconds'].samples[0][2] == 60

    # Disk info (vmguest)
    assert metrics['vmware_vm_guest_disk_capacity'].samples[0][1] == {
        'vm_name': 'vm-1',
        'host_name': 'host-1',
        'cluster_name': 'cluster-1',
        'dc_name': 'dc',
        'partition': '/boot',
    }
    assert metrics['vmware_vm_guest_disk_capacity'].samples[0][2] == 100

    # VM tools info (vmguest)
    assert metrics['vmware_vm_guest_tools_running_status'].samples[0][1] == {
        'vm_name': 'vm-1',
        'host_name': 'host-1',
        'cluster_name': 'cluster-1',
        'dc_name': 'dc',
        'tools_status': 'toolsOk',
    }
    assert metrics['vmware_vm_guest_tools_running_status'].samples[0][2] == 1.0

    assert metrics['vmware_vm_guest_tools_version'].samples[0][1] == {
        'vm_name': 'vm-1',
        'host_name': 'host-1',
        'cluster_name': 'cluster-1',
        'dc_name': 'dc',
        'tools_version': '10336',
    }
    assert metrics['vmware_vm_guest_tools_version'].samples[0][2] == 1.0

    assert metrics['vmware_vm_guest_tools_version_status'].samples[0][1] == {
        'vm_name': 'vm-1',
        'host_name': 'host-1',
        'cluster_name': 'cluster-1',
        'dc_name': 'dc',
        'tools_version_status': 'guestToolsUnmanaged',
    }
    assert metrics['vmware_vm_guest_tools_version_status'].samples[0][2] == 1.0

    # Snapshots
    assert metrics['vmware_vm_snapshots'].samples[0][1] == {
        'vm_name': 'vm-1',
        'host_name': 'host-1',
        'cluster_name': 'cluster-1',
        'dc_name': 'dc',
    }
    assert metrics['vmware_vm_snapshots'].samples[0][2] == 2

    assert metrics['vmware_vm_snapshot_timestamp_seconds'].samples[0][1] == {
        'vm_name': 'vm-1',
        'host_name': 'host-1',
        'cluster_name': 'cluster-1',
        'dc_name': 'dc',
        'vm_snapshot_name': 'snapshot_2',
    }
    assert metrics['vmware_vm_snapshot_timestamp_seconds'].samples[0][2] == 120

    assert metrics['vmware_vm_snapshot_timestamp_seconds'].samples[1][1] == {
        'vm_name': 'vm-1',
        'host_name': 'host-1',
        'cluster_name': 'cluster-1',
        'dc_name': 'dc',
        'vm_snapshot_name': 'snapshot_1',
    }
    assert metrics['vmware_vm_snapshot_timestamp_seconds'].samples[1][2] == 60

    # Max Memory
    assert metrics['vmware_vm_memory_max'].samples[0][1] == {
        'vm_name': 'vm-1',
        'host_name': 'host-1',
        'cluster_name': 'cluster-1',
        'dc_name': 'dc',
    }
    assert metrics['vmware_vm_memory_max'].samples[0][2] == 1024


@pytest_twisted.inlineCallbacks
def test_collect_vm_perf():
    collect_only = {
        'vms': True,
        'vmguests': True,
        'datastores': True,
        'hosts': True,
        'snapshots': True,
    }
    collector = VmwareCollector(
        '127.0.0.1',
        'root',
        'password',
        collect_only,
    )

    metrics = collector._create_metric_containers()

    metric_1 = mock.Mock()
    metric_1.id.counterId = 9
    metric_1.value = [9]

    metric_2 = mock.Mock()
    metric_2.id.counterId = 1
    metric_2.value = [1]

    ent_1 = mock.Mock()
    ent_1.value = [metric_1, metric_2]
    ent_1.entity = vim.ManagedObject('vm:1')

    content = mock.Mock()
    content.perfManager.QueryStats.return_value = [ent_1]
    collector.content = _succeed(content)

    collector.__dict__['counter_ids'] = _succeed({
        'cpu.ready.summation': 1,
        'cpu.usage.average': 2,
        'cpu.usagemhz.average': 3,
        'disk.usage.average': 4,
        'disk.read.average': 5,
        'disk.write.average': 6,
        'mem.usage.average': 7,
        'net.received.average': 8,
        'net.transmitted.average': 9,
    })

    collector.__dict__['vm_labels'] = _succeed({
        'vm:1': ['vm-1', 'host-1', 'dc', 'cluster-1'],
    })

    collector.__dict__['vm_inventory'] = _succeed({
        'vm:1': {
            'name': 'vm-1',
            'obj': vim.ManagedObject('vm-1'),
            'runtime.powerState': 'poweredOn',
        },
        'vm:2': {
            'name': 'vm-2',
            'obj': vim.ManagedObject('vm-2'),
            'runtime.powerState': 'poweredOff',
        },
    })

    yield collector._vmware_get_vm_perf_manager_metrics(metrics)

    # General VM metrics
    assert metrics['vmware_vm_net_transmitted_average'].samples[0][1] == {
        'vm_name': 'vm-1',
        'host_name': 'host-1',
        'cluster_name': 'cluster-1',
        'dc_name': 'dc',
    }
    assert metrics['vmware_vm_net_transmitted_average'].samples[0][2] == 9.0


@pytest_twisted.inlineCallbacks
def test_collect_hosts():
    boot_time = EPOCH + datetime.timedelta(seconds=60)

    collect_only = {
        'vms': True,
        'vmguests': True,
        'datastores': True,
        'hosts': True,
        'snapshots': True,
    }
    collector = VmwareCollector(
        '127.0.0.1',
        'root',
        'password',
        collect_only,
    )
    collector.content = _succeed(mock.Mock())

    collector.__dict__['host_labels'] = _succeed({
        'host:1': ['host-1', 'dc', 'cluster'],
        'host:2': ['host-1', 'dc', 'cluster'],
    })

    metrics = collector._create_metric_containers()

    with mock.patch.object(collector, 'batch_fetch_properties') as batch_fetch_properties:
        batch_fetch_properties.return_value = _succeed({
            'host:1': {
                'id': 'host:1',
                'name': 'host-1',
                'runtime.powerState': 'poweredOn',
                'runtime.bootTime': boot_time,
                'runtime.connectionState': 'connected',
                'runtime.inMaintenanceMode': True,
                'summary.quickStats.overallCpuUsage': 100,
                'summary.hardware.numCpuCores': 12,
                'summary.hardware.cpuMhz': 1000,
                'summary.quickStats.overallMemoryUsage': 1024,
                'summary.hardware.memorySize': 2048 * 1024 * 1024,
            },
            'host:2': {
                'id': 'host:2',
                'name': 'host-2',
                'runtime.powerState': 'poweredOff',
            }
        })
        yield collector._vmware_get_hosts(metrics)
        assert _check_properties(batch_fetch_properties.call_args[0][1])

    assert metrics['vmware_host_memory_max'].samples[0][1] == {
        'host_name': 'host-1',
        'dc_name': 'dc',
        'cluster_name': 'cluster'
    }
    assert metrics['vmware_host_memory_max'].samples[0][2] == 2048
    assert metrics['vmware_host_num_cpu'].samples[0][2] == 12

    # In our test data we hava a host that is powered down - we should have its
    # power_state metric but not any others.
    assert len(metrics['vmware_host_power_state'].samples) == 2
    assert len(metrics['vmware_host_memory_max'].samples) == 1


@pytest_twisted.inlineCallbacks
def test_collect_datastore():
    collect_only = {
        'vms': True,
        'vmguests': True,
        'datastores': True,
        'hosts': True,
        'snapshots': True,
    }
    collector = VmwareCollector(
        '127.0.0.1',
        'root',
        'password',
        collect_only,
    )
    collector.content = _succeed(mock.Mock())

    collector.__dict__['datastore_labels'] = _succeed({
        'datastore-1': ['datastore-1', 'dc', 'ds_cluster'],
    })

    metrics = collector._create_metric_containers()

    with mock.patch.object(collector, 'batch_fetch_properties') as batch_fetch_properties:
        batch_fetch_properties.return_value = _succeed({
            'datastore-1': {
                'name': 'datastore-1',
                'summary.capacity': 0,
                'summary.freeSpace': 0,
                'host': ['host-1'],
                'vm': ['vm-1'],
                'summary.accessible': True,
                'summary.maintenanceMode': 'normal',
            }
        })

        yield collector._vmware_get_datastores(metrics)
        assert _check_properties(batch_fetch_properties.call_args[0][1])

    assert metrics['vmware_datastore_capacity_size'].samples[0][1] == {
        'ds_name': 'datastore-1',
        'dc_name': 'dc',
        'ds_cluster': 'ds_cluster'
    }
    assert metrics['vmware_datastore_capacity_size'].samples[0][2] == 0.0

    assert metrics['vmware_datastore_maintenance_mode'].samples[0][1] == {
        'ds_name': 'datastore-1',
        'dc_name': 'dc',
        'ds_cluster': 'ds_cluster',
        'mode': 'normal'
    }
    assert metrics['vmware_datastore_maintenance_mode'].samples[0][2] == 1.0

    assert metrics['vmware_datastore_accessible'].samples[0][1] == {
        'ds_name': 'datastore-1',
        'dc_name': 'dc',
        'ds_cluster': 'ds_cluster'
    }
    assert metrics['vmware_datastore_accessible'].samples[0][2] == 1.0


@pytest_twisted.inlineCallbacks
def test_collect():
    collect_only = {
        'vms': True,
        'vmguests': True,
        'datastores': True,
        'hosts': True,
        'snapshots': True,
    }
    collector = VmwareCollector(
        '127.0.0.1',
        'root',
        'password',
        collect_only,
        ignore_ssl=True,
    )
    collector.content = _succeed(mock.Mock())

    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(collector, '_vmware_get_vms')).return_value = _succeed(True)
        stack.enter_context(
            mock.patch.object(collector, '_vmware_get_vm_perf_manager_metrics')
        ).return_value = _succeed(True)
        stack.enter_context(mock.patch.object(collector, '_vmware_get_datastores')).return_value = _succeed(True)
        stack.enter_context(mock.patch.object(collector, '_vmware_get_hosts')).return_value = _succeed(True)
        stack.enter_context(mock.patch.object(collector, '_vmware_disconnect')).return_value = _succeed(None)
        metrics = yield collector.collect()

    assert metrics[0].name == 'vmware_vm_power_state'
    assert metrics[-1].name == 'vmware_vm_snapshot_timestamp_seconds'


@pytest_twisted.inlineCallbacks
def test_collect_deferred_error_works():
    collect_only = {
        'vms': True,
        'vmguests': True,
        'datastores': True,
        'hosts': True,
        'snapshots': True,
    }
    collector = VmwareCollector(
        '127.0.0.1',
        'root',
        'password',
        collect_only,
        ignore_ssl=True,
    )
    collector.content = _succeed(mock.Mock())

    @defer.inlineCallbacks
    def _fake_get_vms(*args, **kwargs):
        yield None
        raise RuntimeError('An error has occurred')

    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(collector, '_vmware_get_vms')).side_effect = _fake_get_vms
        stack.enter_context(
            mock.patch.object(collector, '_vmware_get_vm_perf_manager_metrics')
        ).return_value = _succeed(None)
        stack.enter_context(mock.patch.object(collector, '_vmware_get_datastores')).return_value = _succeed(None)
        stack.enter_context(mock.patch.object(collector, '_vmware_get_hosts')).return_value = _succeed(None)
        stack.enter_context(mock.patch.object(collector, '_vmware_disconnect')).return_value = _succeed(None)

        with pytest.raises(defer.FirstError):
            yield collector.collect()


@pytest_twisted.inlineCallbacks
def test_vmware_get_inventory():
    content = mock.Mock()

    # Compute case 1
    host_1 = mock.Mock()
    host_1._moId = 'host:1'
    host_1.name = 'host-1'
    host_1.summary.config.name = 'host-1.'

    folder_1 = mock.Mock()
    folder_1.host = [host_1]

    # Computer case 2
    host_2 = mock.Mock()
    host_2._moId = 'host:2'
    host_2.name = 'host-2'
    host_2.summary.config.name = 'host-2.'

    folder_2 = vim.ClusterComputeResource('computer-cluster:1')
    folder_2.__dict__['name'] = 'compute-cluster-1'
    folder_2.__dict__['host'] = [host_2]

    # Datastore case 1
    datastore_1 = vim.Datastore('datastore:1')
    datastore_1.__dict__['name'] = 'datastore-1'

    # Datastore case 2
    datastore_2 = vim.Datastore('datastore:2')
    datastore_2.__dict__['name'] = 'datastore-2'

    datastore_2_folder = vim.StoragePod('storagepod:1')
    datastore_2_folder.__dict__['childEntity'] = [datastore_2]
    datastore_2_folder.__dict__['name'] = 'datastore2-folder'

    data_center_1 = mock.Mock()
    data_center_1.name = 'dc-1'
    data_center_1.hostFolder.childEntity = [folder_1, folder_2]
    data_center_1.datastoreFolder.childEntity = [datastore_1, datastore_2_folder]

    content.rootFolder.childEntity = [data_center_1]

    collect_only = {
        'vms': True,
        'vmguests': True,
        'datastores': True,
        'hosts': True,
        'snapshots': True,
    }
    collector = VmwareCollector(
        '127.0.0.1',
        'root',
        'password',
        collect_only,
        ignore_ssl=True,
    )
    collector.content = content

    with contextlib.ExitStack() as stack:
        # We have to disable the LazyObject magic on pyvmomi classes so that we can use them as fakes
        stack.enter_context(mock.patch.object(vim.ClusterComputeResource, 'name', None))
        stack.enter_context(mock.patch.object(vim.ClusterComputeResource, 'host', None))
        stack.enter_context(mock.patch.object(vim.Datastore, 'name', None))
        stack.enter_context(mock.patch.object(vim.StoragePod, 'childEntity', None))
        stack.enter_context(mock.patch.object(vim.StoragePod, 'name', None))

        host = yield collector.host_labels
        ds = yield collector.datastore_labels

    assert host == {
        'host:1': ['host-1', 'dc-1', ''],
        'host:2': ['host-2', 'dc-1', 'compute-cluster-1'],
    }

    assert ds == {
        'datastore-1': ['datastore-1', 'dc-1', ''],
        'datastore-2': ['datastore-2', 'dc-1', 'datastore2-folder'],
    }


@pytest_twisted.inlineCallbacks
def test_vmware_connect():
    collect_only = {
        'vms': True,
        'vmguests': True,
        'datastores': True,
        'hosts': True,
        'snapshots': True,
    }
    collector = VmwareCollector(
        '127.0.0.1',
        'root',
        'password',
        collect_only,
        ignore_ssl=True,
    )

    with mock.patch('vmware_exporter.vmware_exporter.connect') as connect:
        yield collector.connection

        call_kwargs = connect.SmartConnect.call_args[1]
        assert call_kwargs['host'] == '127.0.0.1'
        assert call_kwargs['user'] == 'root'
        assert call_kwargs['pwd'] == 'password'
        assert call_kwargs['sslContext'] is not None


@pytest_twisted.inlineCallbacks
def test_vmware_disconnect():
    collect_only = {
        'vms': True,
        'vmguests': True,
        'datastores': True,
        'hosts': True,
        'snapshots': True,
    }
    collector = VmwareCollector(
        '127.0.0.1',
        'root',
        'password',
        collect_only,
    )

    # Mock that we have a connection
    connection = object()
    collector.connection = connection

    with mock.patch('vmware_exporter.vmware_exporter.connect') as connect:
        yield collector._vmware_disconnect()
        connect.Disconnect.assert_called_with(connection)


@pytest_twisted.inlineCallbacks
def test_counter_ids():
    counter = mock.Mock()
    counter.groupInfo.key = 'a'
    counter.nameInfo.key = 'b'
    counter.rollupType = 'c'
    counter.key = 1

    content = mock.Mock()
    content.perfManager.perfCounter = [counter]

    collect_only = {
        'vms': True,
        'vmguests': True,
        'datastores': True,
        'hosts': True,
        'snapshots': True,
    }
    collector = VmwareCollector(
        '127.0.0.1',
        'root',
        'password',
        collect_only,
    )
    collector.content = content

    result = yield collector.counter_ids
    assert result == {'a.b.c': 1}


def test_healthz():
    request = mock.Mock()

    resource = HealthzResource()
    response = resource.render_GET(request)

    request.setResponseCode.assert_called_with(200)

    assert response == b'Server is UP'


def test_vmware_resource():
    request = mock.Mock()

    args = mock.Mock()
    args.config_file = None

    resource = VMWareMetricsResource(args)

    with mock.patch.object(resource, '_async_render_GET') as _async_render_GET:
        assert resource.render_GET(request) == NOT_DONE_YET
        _async_render_GET.assert_called_with(request)


@pytest_twisted.inlineCallbacks
def test_vmware_resource_async_render_GET():
    request = mock.Mock()
    request.args = {
        b'vsphere_host': [b'127.0.0.1'],
    }

    args = mock.Mock()
    args.config_file = None

    resource = VMWareMetricsResource(args)

    with mock.patch('vmware_exporter.vmware_exporter.VmwareCollector') as Collector:
        Collector.return_value.collect.return_value = []
        yield resource._async_render_GET(request)

    request.setResponseCode.assert_called_with(200)
    request.write.assert_called_with(b'')
    request.finish.assert_called_with()


@pytest_twisted.inlineCallbacks
def test_vmware_resource_async_render_GET_errback():
    request = mock.Mock()
    request.args = {
        b'vsphere_host': [b'127.0.0.1'],
    }

    args = mock.Mock()
    args.config_file = None

    resource = VMWareMetricsResource(args)

    with mock.patch('vmware_exporter.vmware_exporter.VmwareCollector') as Collector:
        Collector.return_value.collect.side_effect = RuntimeError('Test exception')
        yield resource._async_render_GET(request)

    request.setResponseCode.assert_called_with(500)
    request.write.assert_called_with(b'# Collection failed')
    request.finish.assert_called_with()


@pytest_twisted.inlineCallbacks
def test_vmware_resource_async_render_GET_no_target():
    request = mock.Mock()
    request.args = {
    }

    args = mock.Mock()
    args.config_file = None

    resource = VMWareMetricsResource(args)

    with mock.patch('vmware_exporter.vmware_exporter.VmwareCollector'):
        yield resource._async_render_GET(request)

    request.setResponseCode.assert_called_with(500)
    request.write.assert_called_with(b'No vsphere_host or target defined!\n')
    request.finish.assert_called_with()


@pytest_twisted.inlineCallbacks
def test_vmware_resource_async_render_GET_section():
    request = mock.Mock()
    request.args = {
        b'target': [b'this-is-ignored'],
        b'section': [b'mysection'],
    }

    args = mock.Mock()
    args.config_file = None

    resource = VMWareMetricsResource(args)
    resource.config = {
        'default': {
            'ignore_ssl': False,
            'vsphere_host': '127.0.0.10',
            'vsphere_user': 'username1',
            'vsphere_password': 'password1',
            'collect_only': {
                'datastores': True,
                'hosts': True,
                'snapshots': True,
                'vmguests': True,
                'vms': True,
            }
        },
        'mysection': {
            'ignore_ssl': 'On',
            'vsphere_host': '127.0.0.11',
            'vsphere_user': 'username2',
            'vsphere_password': 'password2',
            'collect_only': {
                'datastores': True,
                'hosts': True,
                'snapshots': True,
                'vmguests': True,
                'vms': True,
            }
        }
    }

    with mock.patch('vmware_exporter.vmware_exporter.VmwareCollector') as Collector:
        Collector.return_value.collect.return_value = []
        yield resource._async_render_GET(request)

    Collector.assert_called_with(
        '127.0.0.11',
        'username2',
        'password2',
        resource.config['mysection']['collect_only'],
        'On'
    )

    request.setResponseCode.assert_called_with(200)
    request.write.assert_called_with(b'')
    request.finish.assert_called_with()


def test_config_env_multiple_sections():
    env = {
        'VSPHERE_HOST': '127.0.0.10',
        'VSPHERE_USER': 'username1',
        'VSPHERE_PASSWORD': 'password1',
        'VSPHERE_MYSECTION_HOST': '127.0.0.11',
        'VSPHERE_MYSECTION_USER': 'username2',
        'VSPHERE_MYSECTION_PASSWORD': 'password2',
    }

    args = mock.Mock()
    args.config_file = None

    with mock.patch('vmware_exporter.vmware_exporter.os.environ', env):
        resource = VMWareMetricsResource(args)

    assert resource.config == {
        'default': {
            'ignore_ssl': False,
            'vsphere_host': '127.0.0.10',
            'vsphere_user': 'username1',
            'vsphere_password': 'password1',
            'collect_only': {
                'datastores': True,
                'hosts': True,
                'snapshots': True,
                'vmguests': True,
                'vms': True,
            }
        },
        'mysection': {
            'ignore_ssl': False,
            'vsphere_host': '127.0.0.11',
            'vsphere_user': 'username2',
            'vsphere_password': 'password2',
            'collect_only': {
                'datastores': True,
                'hosts': True,
                'snapshots': True,
                'vmguests': True,
                'vms': True,
            }
        }
    }


def test_main():
    with pytest.raises(SystemExit):
        main(['-h'])
