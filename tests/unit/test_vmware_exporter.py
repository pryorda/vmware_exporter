import datetime
from unittest import mock

import pytest_twisted
import pytz
from pyVmomi import vim

from vmware_exporter.vmware_exporter import HealthzResource, VmwareCollector


EPOCH = datetime.datetime(1970, 1, 1, tzinfo=pytz.utc)


@mock.patch('vmware_exporter.vmware_exporter.batch_fetch_properties')
@pytest_twisted.inlineCallbacks
def test_collect_vms(batch_fetch_properties):
    content = mock.Mock()

    boot_time = EPOCH + datetime.timedelta(seconds=60)

    batch_fetch_properties.return_value = {
        'vm-1': {
            'name': 'vm-1',
            'runtime.host': vim.ManagedObject('host-1'),
            'runtime.powerState': 'poweredOn',
            'summary.config.numCpu': 1,
            'runtime.bootTime': boot_time,
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


@mock.patch('vmware_exporter.vmware_exporter.batch_fetch_properties')
def test_collect_hosts(batch_fetch_properties):
    content = mock.Mock()

    batch_fetch_properties.return_value = {
        'host-1': {
            'id': 'host:1',
            'name': 'host-1',
            'runtime.powerState': 'poweredOn',
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


def test_healthz():
    request = mock.Mock()

    resource = HealthzResource()
    response = resource.render_GET(request)

    request.setResponseCode.assert_called_with(200)

    assert response == b'Server is UP'
