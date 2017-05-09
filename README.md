# vmware_exporter
VMWare VCenter Exporter for Prometheus.

Get VMWare VCenter snapshot informations:
- Snapshot count
- Snapshot age (in days)

## Usage

- Create a `config.yml` file based on the `config.yml.sample`.
- Run `$ python vmware_exporter.py`
- Go to http://localhost:8000/metrics to see metrics

## Current Status

- Only VCenter 6 and 6.5 have been tested.
- Only Snapshot information is exported, i.e:
```
# HELP vmware_snapshot_count VMWare Snapshot count
# TYPE vmware_snapshot_count gauge
vmware_snapshot_count{vm_name="My Super Virtual Machine"} 2.0
# HELP vmware_snapshot_age VMWare Snapshot Age
# TYPE vmware_snapshot_age gauge
vmware_snapshot_age{vm_name="My Super Virtual Machine",vm_snapshot_name="Very old snaphot"} 187.0
vmware_snapshot_age{vm_name="My Super Virtual Machine",vm_snapshot_name="Old snapshot"} 183.0
```

## References

The VMWare exporter uses 2 libraries:
- [pyVmomi](https://github.com/vmware/pyvmomi) for VMWare connection
- Prometheus [client_python](https://github.com/prometheus/client_python) for Prometheus supervision

The initial code is mainly inspired from:
- https://www.robustperception.io/writing-a-jenkins-exporter-in-python/
- https://github.com/vmware/pyvmomi-community-samples
- https://github.com/jbidinger/pyvmomi-tools

## License

See LICENSE file
