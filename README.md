# vmware_exporter
VMWare VCenter Exporter for Prometheus.

Get VMWare VCenter information:
- Current number of active snapshots
- Snapshot Unix timestamp creation date
- Datastore size and other stuff
- Basic VM and Host metrics

## Usage

- install with `$ python setup.py install` or `$ pip install vmware_exporter` (Installing from pip will install an old version. This is likely something I wont persue)
- Create a `config.yml` file based on the configuration section. Some variables can be passed in as environment variables
- Run `$ vmware_exporter -c /path/to/your/config`
- Go to http://localhost:9272/metrics?vsphere_host=vcenter.company.com to see metrics

Alternatively, if you don't wish to install the package, run using `$ vmware_exporter/vmware_exporter.py` or you can use the following docker command:

```
docker run -it --rm  -p 9272:9272 -e VSPHERE_USER=${VSPHERE_USERNAME} -e VSPHERE_PASSWORD=${VSPHERE_PASSWORD} -e VSPHERE_HOST=${VSPHERE_HOST} -e VSPHERE_IGNORE_SSL=True --name vmware_exporter pryorda/vmware_exporter
```

### Configuration amd limiting data collection

You do not need to provide a configuration file unless you are not going to use Environment variables. If you do plan to use a configuration file be sure to override the container entrypoint or add -c config.yml to the command args.

If you want to limit the scope of the metrics gather you can update the subsystem under `collect_only` in the config section, e.g. under `default`, or by using the environment variables:

    collect_only:
        vms: False
        datastores: True
        hosts: True

This would only connect datastores and hosts.

You can have multiple sections for different hosts and the configuration would look like:
```
default:
    vsphere_host: "vcenter"
    vsphere_user: "user"
    vsphere_password: "password"
    ignore_ssl: False
    collect_only:
        vms: True
        datastores: True
        hosts: True

esx:
    vsphere_host: vc.example2.com
    vsphere_user: 'root'
    vsphere_password: 'password'
    ignore_ssl: True
    collect_only:
        vms: False
        datastores: False
        hosts: True

limited:
    vsphere_host: slowvc.example.com
    vsphere_user: 'administrator@vsphere.local'
    vsphere_password: 'password'
    ignore_ssl: True
    collect_only:
        vms: False
        datastores: True
        hosts: False
```
 Switching sections can be done by adding ?section=limited to the url.

#### Environment Variables
| Varible                      | Precedence             | Defaults | Description                                      |
| ---------------------------- | ---------------------- | -------- | --------------------------------------- |
| `VSPHERE_HOST`               | config, env, get_param | n/a      | vsphere server to connect to   |
| `VSPHERE_USER`               | config, env            | n/a      | User for connecting to vsphere |
| `VSPHERE_PASSWORD`           | config, env            | n/a      | Password for connecting to vsphere |
| `VSPHERE_IGNORE_SSL`         | config, env            | False    | Ignore the ssl cert on the connection to vsphere host |
| `VSPHERE_COLLECT_HOSTS`      | config, env            | True     | Set to false to disable collect of hosts |
| `VSPHERE_COLLECT_DATASTORES` | config, env            | True     | Set to false to disable collect of datastores |
| `VSPHERE_COLLECT_VMS`        | config, env            | True     | Set to false to disable collect of virtual machines |

### Prometheus configuration

You can use the following parameters in prometheus configuration file. The `params` section is used to manage multiple login/passwords.

```
  - job_name: 'vmware_vcenter'
    metrics_path: '/metrics'
    static_configs:
      - targets:
        - 'vcenter.company.com
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: localhost:9272

  - job_name: 'vmware_esx'
    metrics_path: '/metrics'
    file_sd_configs:
      - files:
        - /etc/prometheus/esx.yml
    params:
      section: [esx]
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: localhost:9272
```

## Current Status

- VCenter and ESXi 6 and 6.5 have been tested.
- VM information, Snapshot, Host and Datastore basic information is exported, i.e:
```
# HELP vmware_snapshots VMWare current number of existing snapshots
# TYPE vmware_snapshot_count gauge
vmware_snapshot_timestamp_seconds{vm_name="My Super Virtual Machine"} 2.0
# HELP vmware_snapshot_timestamp_seconds VMWare Snapshot creation time in seconds
# TYPE vmware_snapshot_timestamp_seconds gauge
vmware_snapshot_age{vm_name="My Super Virtual Machine",vm_snapshot_name="Very old snaphot"} 1478146956.96092
vmware_snapshot_age{vm_name="My Super Virtual Machine",vm_snapshot_name="Old snapshot"} 1478470046.975632

# HELP vmware_datastore_capacity_size VMWare Datasore capacity in bytes
# TYPE vmware_datastore_capacity_size gauge
vmware_datastore_capacity_size{ds_name="ESX1-LOCAL"} 67377299456.0
# HELP vmware_datastore_freespace_size VMWare Datastore freespace in bytes
# TYPE vmware_datastore_freespace_size gauge
vmware_datastore_freespace_size{ds_name="ESX1-LOCAL"} 66349694976.0
# HELP vmware_datastore_uncommited_size VMWare Datastore uncommitted in bytes
# TYPE vmware_datastore_uncommited_size gauge
vmware_datastore_uncommited_size{ds_name="ESX1-LOCAL"} 0.0
# HELP vmware_datastore_provisoned_size VMWare Datastore provisoned in bytes
# TYPE vmware_datastore_provisoned_size gauge
vmware_datastore_provisoned_size{ds_name="ESX1-LOCAL"} 1027604480.0
# HELP vmware_datastore_hosts VMWare Hosts number using this datastore
# TYPE vmware_datastore_hosts gauge
vmware_datastore_hosts{ds_name="ESX1-LOCAL"} 1.0
# HELP vmware_datastore_vms VMWare Virtual Machines number using this datastore
# TYPE vmware_datastore_vms gauge
vmware_datastore_vms{ds_name="ESX1-LOCAL"} 0.0

# HELP vmware_host_power_state VMWare Host Power state (On / Off)
# TYPE vmware_host_power_state gauge
vmware_host_power_state{host_name="esx1.company.com"} 1.0
# HELP vmware_host_cpu_usage VMWare Host CPU usage in Mhz
# TYPE vmware_host_cpu_usage gauge
vmware_host_cpu_usage{host_name="esx1.company.com"} 2959.0
# HELP vmware_host_cpu_max VMWare Host CPU max availability in Mhz
# TYPE vmware_host_cpu_max gauge
vmware_host_cpu_max{host_name="esx1.company.com"} 28728.0
# HELP vmware_host_memory_usage VMWare Host Memory usage in Mbytes
# TYPE vmware_host_memory_usage gauge
vmware_host_memory_usage{host_name="esx1.company.com"} 107164.0
# HELP vmware_host_memory_max VMWare Host Memory Max availability in Mbytes
# TYPE vmware_host_memory_max gauge
vmware_host_memory_max{host_name="esx1.company.com"} 131059.01953125
```

## References

The VMWare exporter uses theses libraries:
- [pyVmomi](https://github.com/vmware/pyvmomi) for VMWare connection
- Prometheus [client_python](https://github.com/prometheus/client_python) for Prometheus supervision
- [Twisted](http://twistedmatrix.com/trac/) for http server

The initial code is mainly inspired from:
- https://www.robustperception.io/writing-a-jenkins-exporter-in-python/
- https://github.com/vmware/pyvmomi-community-samples
- https://github.com/jbidinger/pyvmomi-tools

## Maintainer

Daniel Pryor [pryorda](https://github.com/pryorda)

## License

See LICENSE file
