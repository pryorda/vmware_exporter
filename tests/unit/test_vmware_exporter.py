from unittest import mock

from vmware_exporter.vmware_exporter import VmwareCollector


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
