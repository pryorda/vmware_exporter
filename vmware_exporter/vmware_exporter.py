#!/usr/bin/env python
# -*- python -*-
# -*- coding: utf-8 -*-
"""
Handles collection of metrics for vmware.
"""

from __future__ import print_function
from datetime import datetime

# Generic imports
import argparse
import os
import ssl
from threader import Threader
import pytz
import yaml

from yamlconfig import YamlConfig

# Twisted
from twisted.web.server import Site, NOT_DONE_YET
from twisted.web.resource import Resource
from twisted.internet import reactor, endpoints
from twisted.internet.task import deferLater

# VMWare specific imports
from pyVmomi import vim, vmodl
from pyVim import connect

# Prometheus specific imports
from prometheus_client.core import GaugeMetricFamily, _floatToGoString


class VMWareMetricsResource(Resource):
    """
    VMWare twisted ``Resource`` handling multi endpoints
    Only handle /metrics and /healthz path
    """
    isLeaf = True

    def __init__(self):
        """
        Init Metric Resource
        """
        Resource.__init__(self)
        self.threader = Threader()

    def configure(self, args):
        if args.config_file:
            try:
                self.config = YamlConfig(args.config_file)
                if 'default' not in self.config.keys():
                    log("Error, you must have a default section in config file (for now)")
                    exit(1)
            except Exception as exception:
                raise SystemExit("Error while reading configuration file: {0}".format(exception.message))
        else:
            config_data = """
            default:
                vsphere_host: "{0}"
                vsphere_user: "{1}"
                vsphere_password: "{2}"
                ignore_ssl: {3}
                collect_only:
                    vms: True
                    datastores: True
                    hosts: True
                    snapshots: True
            """.format(os.environ.get('VSPHERE_HOST'),
                       os.environ.get('VSPHERE_USER'),
                       os.environ.get('VSPHERE_PASSWORD'),
                       os.environ.get('VSPHERE_IGNORE_SSL', False)
                       )
            self.config = yaml.load(config_data)
            self.config['default']['collect_only']['hosts'] = os.environ.get('VSPHERE_COLLECT_HOSTS', True)
            self.config['default']['collect_only']['datastores'] = os.environ.get('VSPHERE_COLLECT_DATASTORES', True)
            self.config['default']['collect_only']['vms'] = os.environ.get('VSPHERE_COLLECT_VMS', True)
            self.config['default']['collect_only']['snapshots'] = os.environ.get('VSPHERE_COLLECT_SNAPSHOTS', True)

    def render_GET(self, request):
        """ handles get requests for metrics, health, and everything else """
        path = request.path.decode()
        request.setHeader("Content-Type", "text/plain; charset=UTF-8")
        if path == '/metrics':
            deferred_request = deferLater(reactor, 0, lambda: request)
            deferred_request.addCallback(self.generate_latest_metrics)
            deferred_request.addErrback(self.errback, request)
            return NOT_DONE_YET
        elif path == '/healthz':
            request.setResponseCode(200)
            log("Service is UP")
            return 'Server is UP'.encode()
        else:
            log("Uri not found: " + request.uri)
            request.setResponseCode(404)
            return '404 Not Found'.encode()

    def errback(self, failure, request):
        """ handles failures from requests """
        failure.printTraceback()
        log(failure)
        request.processingFailed(failure)   # This will send a trace to the browser and close the request.
        return None

    def generate_latest_metrics(self, request):
        """ gets the latest metrics """
        section = request.args.get('section', ['default'])[0]
        if self.config[section].get('vsphere_host') and self.config[section].get('vsphere_host') != "None":
            vsphere_host = self.config[section].get('vsphere_host')
        elif request.args.get('target', [None])[0]:
            vsphere_host = request.args.get('target', [None])[0]
        elif request.args.get('vsphere_host', [None])[0]:
            vsphere_host = request.args.get('vsphere_host')[0]
        else:
            request.setResponseCode(500)
            log("No vsphere_host or target defined")
            request.write('No vsphere_host or target defined!\n')
            request.finish()

        output = []
        for metric in self.collect(vsphere_host, section):
            output.append('# HELP {0} {1}'.format(
                metric.name, metric.documentation.replace('\\', r'\\').replace('\n', r'\n')))
            output.append('\n# TYPE {0} {1}\n'.format(metric.name, metric.type))
            for name, labels, value in metric.samples:
                if labels:
                    labelstr = '{{{0}}}'.format(','.join(
                        ['{0}="{1}"'.format(
                            k, v.replace('\\', r'\\').replace('\n', r'\n').replace('"', r'\"'))
                         for k, v in sorted(labels.items())]))
                else:
                    labelstr = ''
                if isinstance(value, int):
                    value = float(value)
                if isinstance(value, long):  # noqa: F821
                    value = float(value)
                if isinstance(value, float):
                    output.append('{0}{1} {2}\n'.format(name, labelstr, _floatToGoString(value)))
        if output != []:
            request.write(''.join(output).encode('utf-8'))
            request.finish()
        else:
            request.setResponseCode(500, message=('cannot connect to vmware'))
            request.finish()
            return

    def collect(self, vsphere_host, section='default'):
        """ collects metrics """
        if section not in self.config.keys():
            log("{} is not a valid section, using default".format(section))
            section = 'default'
        host_inventory = {}
        ds_inventory = {}
        metric_list = {}
        metric_list['vms'] = {
            'vmware_vm_power_state': GaugeMetricFamily(
                'vmware_vm_power_state',
                'VMWare VM Power state (On / Off)',
                labels=['vm_name', 'host_name', 'dc_name', 'cluster_name']),
            'vmware_vm_boot_timestamp_seconds': GaugeMetricFamily(
                'vmware_vm_boot_timestamp_seconds',
                'VMWare VM boot time in seconds',
                labels=['vm_name', 'host_name', 'dc_name', 'cluster_name']),
            'vmware_vm_num_cpu': GaugeMetricFamily(
                'vmware_vm_num_cpu',
                'VMWare Number of processors in the virtual machine',
                labels=['vm_name', 'host_name', 'dc_name', 'cluster_name']),
            'vmware_vm_guest_disk_free': GaugeMetricFamily(
                'vmware_vm_guest_disk_free',
                'Disk metric per partition',
                labels=['vm_name', 'host_name', 'dc_name', 'cluster_name', 'partition', ]),
            'vmware_vm_guest_disk_capacity': GaugeMetricFamily(
                'vmware_vm_guest_disk_capacity',
                'Disk capacity metric per partition',
                labels=['vm_name', 'host_name', 'dc_name', 'cluster_name', 'partition', ]),
            }
        metric_list['snapshots'] = {
            'vmware_vm_snapshots': GaugeMetricFamily(
                'vmware_vm_snapshots',
                'VMWare current number of existing snapshots',
                labels=['vm_name', 'host_name', 'dc_name', 'cluster_name']),
            'vmware_vm_snapshot_timestamp_seconds': GaugeMetricFamily(
                'vmware_vm_snapshot_timestamp_seconds',
                'VMWare Snapshot creation time in seconds',
                labels=['vm_name', 'host_name', 'dc_name', 'cluster_name', 'vm_snapshot_name']),
            }
        metric_list['datastores'] = {
            'vmware_datastore_capacity_size': GaugeMetricFamily(
                'vmware_datastore_capacity_size',
                'VMWare Datasore capacity in bytes',
                labels=['ds_name', 'dc_name', 'ds_cluster']),
            'vmware_datastore_freespace_size': GaugeMetricFamily(
                'vmware_datastore_freespace_size',
                'VMWare Datastore freespace in bytes',
                labels=['ds_name', 'dc_name', 'ds_cluster']),
            'vmware_datastore_uncommited_size': GaugeMetricFamily(
                'vmware_datastore_uncommited_size',
                'VMWare Datastore uncommitted in bytes',
                labels=['ds_name', 'dc_name', 'ds_cluster']),
            'vmware_datastore_provisoned_size': GaugeMetricFamily(
                'vmware_datastore_provisoned_size',
                'VMWare Datastore provisoned in bytes',
                labels=['ds_name', 'dc_name', 'ds_cluster']),
            'vmware_datastore_hosts': GaugeMetricFamily(
                'vmware_datastore_hosts',
                'VMWare Hosts number using this datastore',
                labels=['ds_name', 'dc_name', 'ds_cluster']),
            'vmware_datastore_vms': GaugeMetricFamily(
                'vmware_datastore_vms',
                'VMWare Virtual Machines count per datastore',
                labels=['ds_name', 'dc_name', 'ds_cluster']),
            'vmware_datastore_maintenance_mode': GaugeMetricFamily(
                'vmware_datastore_maintenance_mode',
                'VMWare datastore maintenance mode (normal / inMaintenance / enteringMaintenance)',
                labels=['ds_name', 'dc_name', 'ds_cluster', 'mode']),
            'vmware_datastore_type': GaugeMetricFamily(
                'vmware_datastore_type',
                'VMWare datastore type (VMFS, NetworkFileSystem, NetworkFileSystem41, CIFS, VFAT, VSAN, VFFS)',
                labels=['ds_name', 'dc_name', 'ds_cluster', 'ds_type']),
            'vmware_datastore_accessible': GaugeMetricFamily(
                'vmware_datastore_accessible',
                'VMWare datastore accessible (true / false)',
                labels=['ds_name', 'dc_name', 'ds_cluster'])
            }
        metric_list['hosts'] = {
            'vmware_host_power_state': GaugeMetricFamily(
                'vmware_host_power_state',
                'VMWare Host Power state (On / Off)',
                labels=['host_name', 'dc_name', 'cluster_name']),
            'vmware_host_connection_state': GaugeMetricFamily(
                'vmware_host_connection_state',
                'VMWare Host connection state (connected / disconnected / notResponding)',
                labels=['host_name', 'dc_name', 'cluster_name', 'state']),
            'vmware_host_maintenance_mode': GaugeMetricFamily(
                'vmware_host_maintenance_mode',
                'VMWare Host maintenance mode (true / false)',
                labels=['host_name', 'dc_name', 'cluster_name']),
            'vmware_host_boot_timestamp_seconds': GaugeMetricFamily(
                'vmware_host_boot_timestamp_seconds',
                'VMWare Host boot time in seconds',
                labels=['host_name', 'dc_name', 'cluster_name']),
            'vmware_host_cpu_usage': GaugeMetricFamily(
                'vmware_host_cpu_usage',
                'VMWare Host CPU usage in Mhz',
                labels=['host_name', 'dc_name', 'cluster_name']),
            'vmware_host_cpu_max': GaugeMetricFamily(
                'vmware_host_cpu_max',
                'VMWare Host CPU max availability in Mhz',
                labels=['host_name', 'dc_name', 'cluster_name']),
            'vmware_host_memory_usage': GaugeMetricFamily(
                'vmware_host_memory_usage',
                'VMWare Host Memory usage in Mbytes',
                labels=['host_name', 'dc_name', 'cluster_name']),
            'vmware_host_memory_max': GaugeMetricFamily(
                'vmware_host_memory_max',
                'VMWare Host Memory Max availability in Mbytes',
                labels=['host_name', 'dc_name', 'cluster_name']),
            }

        metrics = {}
        for key, value in self.config[section]['collect_only'].items():
            if value is True:
                metrics.update(metric_list[key])

        log("Start collecting metrics from {0}".format(vsphere_host))

        self.vmware_connection = self._vmware_connect(vsphere_host, section)
        if not self.vmware_connection:
            log("Cannot connect to vmware")
            return

        content = self.vmware_connection.RetrieveContent()

        # Generate inventory dict
        log("Starting inventory collection")
        host_inventory, ds_inventory = self._vmware_get_inventory(content)
        log("Finished inventory collection")

        # Collect VMs metrics
        if self.config[section]['collect_only']['vms'] is True:
            log("Starting VM performance metrics collection")
            counter_info = self._vmware_perf_metrics(content)
            self._vmware_get_vms(content, metrics, counter_info, host_inventory)
            log("Finished VM performance metrics collection")

        # Collect Snapshots (count and age)
        if self.config[section]['collect_only']['snapshots'] is True:
            log("Starting VM snapshot metric collection")
            vm_snap_counts, vm_snap_ages = self._vmware_get_snapshots(content, host_inventory)
            for v in vm_snap_counts:
                metrics['vmware_vm_snapshots'].add_metric([v['vm_name'], v['vm_host_name'],
                                                          v['vm_dc_name'], v['vm_cluster_name']],
                                                          v['vm_snapshot_count'])
            for vm_snap_age in vm_snap_ages:
                for v in vm_snap_age:
                    metrics['vmware_vm_snapshot_timestamp_seconds'].add_metric([v['vm_name'], v['vm_host_name'],
                                                                               v['vm_dc_name'], v['vm_cluster_name'],
                                                                               v['vm_snapshot_name']],
                                                                               v['vm_snapshot_timestamp_seconds'])
            log("Finished VM snapshot metric collection")

        # Collect Datastore metrics
        if self.config[section]['collect_only']['datastores'] is True:
            log("Starting datastore metrics collection")
            self._vmware_get_datastores(content, metrics, ds_inventory)
            log("Finished datastore metrics collection")

        # Collect Hosts metrics
        if self.config[section]['collect_only']['hosts'] is True:
            log("Starting host metrics collection")
            self._vmware_get_hosts(content, metrics, host_inventory)
            log("Finished host metrics collection")

        log("Finished collecting metrics from {0}".format(vsphere_host))
        self.threader.join()
        self._vmware_disconnect()

        for _key, metric in metrics.items():
            yield metric

    def _to_epoch(self, my_date):
        """ convert to epoch time """
        return (my_date - datetime(1970, 1, 1, tzinfo=pytz.utc)).total_seconds()

    def _vmware_get_obj(self, content, vimtype, name=None):
        """
         Get the vsphere object associated with a given text name
        """
        obj = None
        container = content.viewManager.CreateContainerView(
            content.rootFolder, vimtype, True)
        if name:
            for view in container.view:
                if view.name == name:
                    obj = view
                    return [obj]
        else:
            return container.view

    def _vmware_connect(self, vsphere_host, section):
        """
        Connect to Vcenter and get connection
        """
        vsphere_user = self.config[section].get('vsphere_user')
        vsphere_password = self.config[section].get('vsphere_password')

        context = None
        if self.config[section].get('ignore_ssl') and \
                hasattr(ssl, "_create_unverified_context"):
            context = ssl._create_unverified_context()

        try:
            vmware_connect = connect.SmartConnect(host=vsphere_host,
                                                  user=vsphere_user,
                                                  pwd=vsphere_password,
                                                  sslContext=context)
            return vmware_connect

        except vmodl.MethodFault as error:
            log("Caught vmodl fault: " + error.msg)
            return None

    def _vmware_disconnect(self):
        """
        Disconnect from Vcenter
        """
        connect.Disconnect(self.vmware_connection)

    def _vmware_perf_metrics(self, content):
        """
        create a mapping from performance stats to their counterIDs
        counter_info: [performance stat => counterId]
        performance stat example: cpu.usagemhz.LATEST
        """
        counter_info = {}
        for counter in content.perfManager.perfCounter:
            prefix = counter.groupInfo.key
            counter_full = "{}.{}.{}".format(prefix, counter.nameInfo.key, counter.rollupType)
            counter_info[counter_full] = counter.key
        return counter_info

    def _vmware_full_snapshots_list(self, snapshots):
        """
        Get snapshots from a VM list, recursively
        """
        snapshot_data = []
        for snapshot in snapshots:
            snap_timestamp = self._to_epoch(snapshot.createTime)
            snap_info = {'vm_snapshot_name': snapshot.name, 'vm_snapshot_timestamp_seconds': snap_timestamp}
            snapshot_data.append(snap_info)
            snapshot_data = snapshot_data + self._vmware_full_snapshots_list(
                snapshot.childSnapshotList)
        return snapshot_data

    def _vmware_get_snapshot_details(self, snapshots_count_table, snapshots_age_table, virtual_machine, inventory):
        """
        Gathers snapshot details
        """
        snapshot_paths = self._vmware_full_snapshots_list(virtual_machine.snapshot.rootSnapshotList)

        _, host_name, dc_name, cluster_name = self._vmware_vm_metadata(inventory, virtual_machine)

        for snapshot_path in snapshot_paths:
            snapshot_path['vm_name'] = virtual_machine.name
            snapshot_path['vm_host_name'] = host_name
            snapshot_path['vm_dc_name'] = dc_name
            snapshot_path['vm_cluster_name'] = cluster_name

        # Add Snapshot count per VM
        snapshot_count = len(snapshot_paths)
        snapshot_count_info = {
            'vm_name': virtual_machine.name,
            'vm_host_name': host_name,
            'vm_dc_name': dc_name,
            'vm_cluster_name': cluster_name,
            'vm_snapshot_count': snapshot_count
        }
        snapshots_count_table.append(snapshot_count_info)
        snapshots_age_table.append(snapshot_paths)

    def _vmware_get_snapshots(self, content, inventory):
        """
        Get snapshots from all VM
        """
        snapshots_count_table = []
        snapshots_age_table = []
        virtual_machines = self._vmware_get_obj(content, [vim.VirtualMachine])
        for virtual_machine in virtual_machines:
            if not virtual_machine or virtual_machine.snapshot is None:
                continue
            else:
                self.threader.thread_it(self._vmware_get_snapshot_details,
                                        [snapshots_count_table, snapshots_age_table, virtual_machine, inventory])
        return snapshots_count_table, snapshots_age_table

    def _vmware_get_datastores(self, content, ds_metrics, inventory):
        """
        Get Datastore information
        """
        datastores = self._vmware_get_obj(content, [vim.Datastore])
        for datastore in datastores:
            # ds.RefreshDatastoreStorageInfo()
            summary = datastore.summary
            ds_name = summary.name
            dc_name = inventory[ds_name]['dc']
            ds_cluster = inventory[ds_name]['ds_cluster']

            self.threader.thread_it(self._vmware_get_datastore_metrics,
                                    [datastore, dc_name, ds_cluster, ds_metrics, summary])

    def _vmware_get_datastore_metrics(self, datastore, dc_name, ds_cluster, ds_metrics, summary):
        """
        Get datastore metrics
        """
        ds_capacity = float(summary.capacity)
        ds_freespace = float(summary.freeSpace)
        ds_uncommitted = float(summary.uncommitted) if summary.uncommitted else 0
        ds_provisioned = ds_capacity - ds_freespace + ds_uncommitted

        ds_metrics['vmware_datastore_capacity_size'].add_metric([summary.name, dc_name, ds_cluster], ds_capacity)
        ds_metrics['vmware_datastore_freespace_size'].add_metric([summary.name, dc_name, ds_cluster], ds_freespace)
        ds_metrics['vmware_datastore_uncommited_size'].add_metric([summary.name, dc_name, ds_cluster], ds_uncommitted)
        ds_metrics['vmware_datastore_provisoned_size'].add_metric([summary.name, dc_name, ds_cluster], ds_provisioned)
        ds_metrics['vmware_datastore_hosts'].add_metric([summary.name, dc_name, ds_cluster], len(datastore.host))
        ds_metrics['vmware_datastore_vms'].add_metric([summary.name, dc_name, ds_cluster], len(datastore.vm))
        ds_metrics['vmware_datastore_maintenance_mode'].add_metric([summary.name, dc_name,
                                                                   ds_cluster, summary.maintenanceMode],
                                                                   1)
        ds_metrics['vmware_datastore_type'].add_metric([summary.name, dc_name, ds_cluster, summary.type], 1)
        ds_metrics['vmware_datastore_accessible'].add_metric([summary.name, dc_name, ds_cluster], summary.accessible*1)

    def _vmware_get_vms(self, content, vm_metrics, counter_info, inventory):
        """
        Get VM information
        """

        # List of performance counter we want
        perf_list = [
            'cpu.ready.summation',
            'cpu.usage.average',
            'cpu.usagemhz.average',
            'disk.usage.average',
            'disk.read.average',
            'disk.write.average',
            'mem.usage.average',
            'net.received.average',
            'net.transmitted.average',
        ]

        # Prepare gauges
        for p in perf_list:
            p_metric = 'vmware_vm_' + p.replace('.', '_')
            vm_metrics[p_metric] = GaugeMetricFamily(
                p_metric,
                p_metric,
                labels=['vm_name', 'host_name', 'dc_name', 'cluster_name'])

        virtual_machines = self._vmware_get_obj(content, [vim.VirtualMachine])
        log("Total Virtual Machines: {0}".format(len(virtual_machines)))
        for virtual_machine in virtual_machines:
            self.threader.thread_it(self._vmware_get_vm_perf_metrics,
                                    [content, counter_info, perf_list, virtual_machine, vm_metrics, inventory])

    def _vmware_get_vm_perf_metrics(self, content, counter_info, perf_list, virtual_machine, vm_metrics, inventory):
        """
        Loops over metrics in perf_list on vm
        """
        # DEBUG ME: log("Starting VM: " + vm.name)

        summary = virtual_machine.summary

        vm_power_state = 1 if summary.runtime.powerState == 'poweredOn' else 0
        vm_num_cpu = summary.config.numCpu

        vm_name, vm_host_name, vm_dc_name, vm_cluster_name = self._vmware_vm_metadata(inventory, virtual_machine,
                                                                                      summary)
        vm_metadata = [vm_name, vm_host_name, vm_dc_name, vm_cluster_name]

        # We gather disk metrics
        if len(virtual_machine.guest.disk) > 0:
            [vm_metrics['vmware_vm_guest_disk_free'].add_metric(
             [vm_name, vm_host_name, vm_dc_name, vm_cluster_name, disk.diskPath], disk.freeSpace)
             for disk in virtual_machine.guest.disk]

            [vm_metrics['vmware_vm_guest_disk_capacity'].add_metric(
             [vm_name, vm_host_name, vm_dc_name, vm_cluster_name, disk.diskPath], disk.capacity)
             for disk in virtual_machine.guest.disk]

        vm_metrics['vmware_vm_power_state'].add_metric([vm_name, vm_host_name,
                                                       vm_dc_name, vm_cluster_name],
                                                       vm_power_state)
        vm_metrics['vmware_vm_num_cpu'].add_metric(vm_metadata,
                                                   vm_num_cpu)

        # Get metrics for poweredOn vms only
        if vm_power_state:
            if summary.runtime.bootTime:
                vm_metrics['vmware_vm_boot_timestamp_seconds'].add_metric(
                    vm_metadata,
                    self._to_epoch(summary.runtime.bootTime))

            for p in perf_list:
                self.threader.thread_it(self._vmware_get_vm_perf_metric,
                                        [content, counter_info, p, virtual_machine,
                                         vm_metrics, vm_metadata])

        # Debug Me. log("Finished VM: " + vm.name)

    def _vmware_get_vm_perf_metric(self, content, counter_info, perf_metric,
                                   virtual_machine, vm_metrics, vm_metadata):
        """
        Get vm perf metric
        """

        perf_metric_name = 'vmware_vm_' + perf_metric.replace('.', '_')
        counter_key = counter_info[perf_metric]
        metric_id = vim.PerformanceManager.MetricId(
            counterId=counter_key,
            instance=''
            )
        spec = vim.PerformanceManager.QuerySpec(
            maxSample=1,
            entity=virtual_machine,
            metricId=[metric_id],
            intervalId=20
            )
        result = content.perfManager.QueryStats(querySpec=[spec])
        # DEBUG ME: log("{0} {1}: {2}".format(vm.name, p, float(sum(result[0].value[0].value))))
        try:
            vm_metrics[perf_metric_name].add_metric(vm_metadata,
                                                    float(sum(result[0].value[0].value)))
        except:  # noqa: E722
            log("Error, cannot get vm metric {0} for {1}".format(perf_metric_name,
                                                                 vm_metadata))

    def _vmware_get_hosts(self, content, host_metrics, inventory):
        """
        Get Host (ESXi) information
        """
        hosts = self._vmware_get_obj(content, [vim.HostSystem])
        for host in hosts:
            summary = host.summary
            host_name, host_dc_name, host_cluster_name = self._vmware_host_metadata(inventory, host)

            # Power state
            power_state = 1 if summary.runtime.powerState == 'poweredOn' else 0
            host_metrics['vmware_host_power_state'].add_metric([host_name, host_dc_name, host_cluster_name],
                                                               power_state)

            if power_state:
                self.threader.thread_it(self._vmware_get_host_metrics,
                                        [host_name, host_dc_name, host_cluster_name, host_metrics, summary])

    def _vmware_get_host_metrics(self, host_name, host_dc_name, host_cluster_name, host_metrics, summary):
        """
        Get Host Metrics
        """
        if summary.runtime.bootTime:
            # Host uptime
            host_metrics['vmware_host_boot_timestamp_seconds'].add_metric([host_name, host_dc_name, host_cluster_name],
                                                                          self._to_epoch(
                                                                              summary.runtime.bootTime)
                                                                          )

            # Host connection state (connected, disconnected, notResponding)
            host_metrics['vmware_host_connection_state'].add_metric([host_name, host_dc_name, host_cluster_name,
                                                                    summary.runtime.connectionState],
                                                                    1)

            # Host in maintenance mode?
            host_metrics['vmware_host_maintenance_mode'].add_metric([host_name, host_dc_name, host_cluster_name],
                                                                    summary.runtime.inMaintenanceMode*1)

        # CPU Usage (in Mhz)
        host_metrics['vmware_host_cpu_usage'].add_metric([host_name, host_dc_name, host_cluster_name],
                                                         summary.quickStats.overallCpuUsage)
        cpu_core_num = summary.hardware.numCpuCores
        cpu_total = summary.hardware.cpuMhz * cpu_core_num
        host_metrics['vmware_host_cpu_max'].add_metric([host_name, host_dc_name, host_cluster_name],
                                                       cpu_total)

        # Memory Usage (in MB)
        host_metrics['vmware_host_memory_usage'].add_metric([host_name, host_dc_name, host_cluster_name],
                                                            summary.quickStats.overallMemoryUsage)
        host_metrics['vmware_host_memory_max'].add_metric([host_name, host_dc_name, host_cluster_name],
                                                          float(summary.hardware.memorySize) / 1024 / 1024)

    def _vmware_get_inventory(self, content):
        """
        Get host and datastore inventory (datacenter, cluster) information
        """
        host_inventory = {}
        ds_inventory = {}

        children = content.rootFolder.childEntity
        for child in children:  # Iterate though DataCenters
            dc = child
            hostFolders = dc.hostFolder.childEntity
            for folder in hostFolders:  # Iterate through host folders
                if isinstance(folder, vim.ClusterComputeResource):  # Folder is a Cluster
                    hosts = folder.host
                    for host in hosts:  # Iterate through Hosts in the Cluster
                        host_name = host.summary.config.name
                        host_inventory[host_name] = {}
                        host_inventory[host_name]['dc'] = dc.name
                        host_inventory[host_name]['cluster'] = folder.name
                else:  # Unclustered host
                    host_name = folder.name
                    host_inventory[host_name] = {}
                    host_inventory[host_name]['dc'] = dc.name
                    host_inventory[host_name]['cluster'] = ''

            dsFolders = dc.datastoreFolder.childEntity
            for folder in dsFolders:  # Iterate through datastore folders
                if isinstance(folder, vim.Datastore):  # Unclustered datastore
                    ds_inventory[folder.name] = {}
                    ds_inventory[folder.name]['dc'] = dc.name
                    ds_inventory[folder.name]['ds_cluster'] = ''
                else:  # Folder is a Datastore Cluster
                    datastores = folder.childEntity
                    for datastore in datastores:
                        ds_inventory[datastore.name] = {}
                        ds_inventory[datastore.name]['dc'] = dc.name
                        ds_inventory[datastore.name]['ds_cluster'] = folder.name

        return host_inventory, ds_inventory

    def _vmware_vm_metadata(self, inventory, vm, summary=None):
        """
        Get VM metadata from inventory
        """
        if summary is None:
            summary = vm.summary
        vm_name = vm.name
        vm_host = summary.runtime.host
        vm_host_name = vm_host.name
        vm_dc_name = inventory[vm_host_name]['dc']
        vm_cluster_name = inventory[vm_host_name]['cluster']

        return vm_name, vm_host_name, vm_dc_name, vm_cluster_name

    def _vmware_host_metadata(self, inventory, host):
        """
        Get Host metadata from inventory
        """
        host_name = host.name
        host_dc_name = inventory[host_name]['dc']
        host_cluster_name = inventory[host_name]['cluster']

        return host_name, host_dc_name, host_cluster_name


def log(data):
    """
    Log any message in a uniform format
    """
    print("[{0}] {1}".format(datetime.utcnow().replace(tzinfo=pytz.utc), data))


def main():
    """ start up twisted reactor """
    parser = argparse.ArgumentParser(description='VMWare metrics exporter for Prometheus')
    parser.add_argument('-c', '--config', dest='config_file',
                        default=None, help="configuration file")
    parser.add_argument('-p', '--port', dest='port', type=int,
                        default=9272, help="HTTP port to expose metrics")

    args = parser.parse_args()

    # Start up the server to expose the metrics.
    root = VMWareMetricsResource()
    root.configure(args)
    root.putChild(b'metrics', VMWareMetricsResource())
    root.putChild(b'healthz', VMWareMetricsResource())

    factory = Site(root)
    log("Starting web server on port {}".format(args.port))
    endpoint = endpoints.TCP4ServerEndpoint(reactor, args.port)
    endpoint.listen(factory)
    reactor.run()


if __name__ == '__main__':
    main()
