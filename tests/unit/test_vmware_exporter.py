import contextlib
import datetime
from unittest import mock

import pytest_twisted
import pytz
from pyVmomi import vim
from twisted.internet import defer

from vmware_exporter.vmware_exporter import HealthzResource, VmwareCollector, VMWareMetricsResource


EPOCH = datetime.datetime(1970, 1, 1, tzinfo=pytz.utc)


@mock.patch('vmware_exporter.vmware_exporter.batch_fetch_properties')
@pytest_twisted.inlineCallbacks
def test_collect_vms(batch_fetch_properties):
    content = mock.Mock()

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

    batch_fetch_properties.return_value = {
        'vm-1': {
            'name': 'vm-1',
            'runtime.host': vim.ManagedObject('host-1'),
            'runtime.powerState': 'poweredOn',
            'summary.config.numCpu': 1,
            'runtime.bootTime': boot_time,
            'snapshot': snapshot,
            'guest.disk': [disk],
        }
    }

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

    inventory = {
        'host-1': {
            'name': 'host-1',
            'dc': 'dc',
            'cluster': 'cluster-1',
        }
    }

    metrics = collector._create_metric_containers()

    collector._labels = {}

    with mock.patch.object(collector, '_vmware_get_vm_perf_manager_metrics'):
        yield collector._vmware_get_vms(content, metrics, inventory)

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


@pytest_twisted.inlineCallbacks
def test_collect_vm_perf():
    content = mock.Mock()

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

    inventory = {
        'host-1': {
            'name': 'host-1',
            'dc': 'dc',
            'cluster': 'cluster-1',
        }
    }

    metrics = collector._create_metric_containers()

    collector._labels = {'vm:1': ['vm-1', 'host-1', 'dc', 'cluster-1']}

    vms = {
        'vm-1': {
            'name': 'vm-1',
            'obj': vim.ManagedObject('vm-1'),
            'runtime.powerState': 'poweredOn',
        }
    }

    metric_1 = mock.Mock()
    metric_1.id.counterId = 9
    metric_1.value = [9]

    metric_2 = mock.Mock()
    metric_2.id.counterId = 1
    metric_2.value = [1]

    ent_1 = mock.Mock()
    ent_1.value = [metric_1, metric_2]
    ent_1.entity = vim.ManagedObject('vm:1')

    content.perfManager.QueryStats.return_value = [ent_1]

    with mock.patch.object(collector, '_vmware_perf_metrics') as _vmware_perf_metrics:
        _vmware_perf_metrics.return_value = {
            'cpu.ready.summation': 1,
            'cpu.usage.average': 2,
            'cpu.usagemhz.average': 3,
            'disk.usage.average': 4,
            'disk.read.average': 5,
            'disk.write.average': 6,
            'mem.usage.average': 7,
            'net.received.average': 8,
            'net.transmitted.average': 9,
        }

        yield collector._vmware_get_vm_perf_manager_metrics(content, vms, metrics, inventory)

    # General VM metrics
    assert metrics['vmware_vm_net_transmitted_average'].samples[0][1] == {
        'vm_name': 'vm-1',
        'host_name': 'host-1',
        'cluster_name': 'cluster-1',
        'dc_name': 'dc',
    }
    assert metrics['vmware_vm_net_transmitted_average'].samples[0][2] == 9.0


@mock.patch('vmware_exporter.vmware_exporter.batch_fetch_properties')
def test_collect_hosts(batch_fetch_properties):
    content = mock.Mock()

    boot_time = EPOCH + datetime.timedelta(seconds=60)

    batch_fetch_properties.return_value = {
        'host-1': {
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
        }
    }

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

    inventory = {
        'host:1': {
            'dc': 'dc',
            'cluster': 'cluster',
        }
    }

    metrics = collector._create_metric_containers()
    collector._vmware_get_hosts(content, metrics, inventory)

    assert metrics['vmware_host_memory_max'].samples[0][1] == {
        'host_name': 'host-1',
        'dc_name': 'dc',
        'cluster_name': 'cluster'
    }
    assert metrics['vmware_host_memory_max'].samples[0][2] == 2048


@mock.patch('vmware_exporter.vmware_exporter.batch_fetch_properties')
def test_collect_datastore(batch_fetch_properties):
    content = mock.Mock()

    batch_fetch_properties.return_value = {
        'datastore-1': {
            'name': 'datastore-1',
            'summary.capacity': 0,
            'summary.freeSpace': 0,
            'host': ['host-1'],
            'vm': ['vm-1'],
            'summary.accessible': True,
            'summary.maintenanceMode': 'normal',
        }
    }

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

    inventory = {
        'datastore-1': {
            'dc': 'dc',
            'ds_cluster': 'ds_cluster',
        }
    }

    metrics = collector._create_metric_containers()
    collector._vmware_get_datastores(content, metrics, inventory)

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

    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(collector, '_vmware_connect'))
        get_inventory = stack.enter_context(mock.patch.object(collector, '_vmware_get_inventory'))
        get_inventory.return_value = ([], [])
        stack.enter_context(mock.patch.object(collector, '_vmware_get_vms')).return_value = defer.succeed(None)
        stack.enter_context(mock.patch.object(collector, '_vmware_get_datastores'))
        stack.enter_context(mock.patch.object(collector, '_vmware_get_hosts'))
        stack.enter_context(mock.patch.object(collector, '_vmware_disconnect'))
        metrics = yield collector.collect()

    assert metrics[0].name == 'vmware_vm_power_state'
    assert metrics[-1].name == 'vmware_vm_snapshot_timestamp_seconds'


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
        collector._vmware_connect()

        call_kwargs = connect.SmartConnect.call_args[1]
        assert call_kwargs['host'] == '127.0.0.1'
        assert call_kwargs['user'] == 'root'
        assert call_kwargs['pwd'] == 'password'
        assert call_kwargs['sslContext'] is not None


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
    collector.vmware_connection = connection

    with mock.patch('vmware_exporter.vmware_exporter.connect') as connect:
        collector._vmware_disconnect()
        connect.Disconnect.assert_called_with(connection)


def test_vmware_perf_metrics():
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

    result = collector._vmware_perf_metrics(content)

    assert result == {'a.b.c': 1}


def test_healthz():
    request = mock.Mock()

    resource = HealthzResource()
    response = resource.render_GET(request)

    request.setResponseCode.assert_called_with(200)

    assert response == b'Server is UP'


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
