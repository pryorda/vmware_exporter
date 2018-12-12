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
from concurrent.futures import ThreadPoolExecutor
import os
import ssl
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
from prometheus_client.core import GaugeMetricFamily
from prometheus_client import CollectorRegistry, generate_latest


class VmwareCollector():

    THREAD_LIMIT = 25

    def __init__(self, host, username, password, collect_only, ignore_ssl=False):
        self.threader = ThreadPoolExecutor(max_workers=self.THREAD_LIMIT)

        self.host = host
        self.username = username
        self.password = password
        self.ignore_ssl = ignore_ssl
        self.collect_only = collect_only

    def thread_it(self, method, data):
        # FIXME: Just call submit directly
        self.threader.submit(method, *data)

    def collect(self):
        """ collects metrics """
        vsphere_host = self.host

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
            }
        metric_list['vmguests'] = {
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
        for key, value in self.collect_only.items():
            if value is True:
                metrics.update(metric_list[key])

        log("Start collecting metrics from {0}".format(vsphere_host))

        self.vmware_connection = self._vmware_connect()
        if not self.vmware_connection:
            log(b"Cannot connect to vmware")
            return

        content = self.vmware_connection.RetrieveContent()

        # Generate inventory dict
        log("Starting inventory collection")
        host_inventory, ds_inventory = self._vmware_get_inventory(content)
        log("Finished inventory collection")

        self._labels = {}

        collect_only = self.collect_only

        # Collect Datastore metrics
        if collect_only['datastores'] is True:
            self.threader.submit(
                self._vmware_get_datastores,
                content, metrics, ds_inventory,
            )

        # Collect Hosts metrics
        if collect_only['hosts'] is True:
            self.threader.submit(
                self._vmware_get_hosts,
                content, metrics, host_inventory,
            )

        # Collect VMs metrics
        if collect_only['vmguests'] is True or collect_only['vms'] is True or collect_only['snapshots'] is True:
            log("Starting VM Guests metrics collection")
            virtual_machines = self._vmware_get_vmguests(content, metrics, host_inventory)
            log("Finished VM Guests metrics collection")

        self.threader.shutdown(wait=True)

        if collect_only['vms'] is True:
            counter_info = self._vmware_perf_metrics(content)
            self._vmware_get_vm_perf_manager_metrics(
                content, counter_info, virtual_machines, metrics, host_inventory
            )

        self._vmware_disconnect()
        log("Finished collecting metrics from {0}".format(vsphere_host))

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

    def _vmware_connect(self):
        """
        Connect to Vcenter and get connection
        """
        context = None
        if self.ignore_ssl:
            context = ssl._create_unverified_context()

        try:
            vmware_connect = connect.SmartConnect(
                host=self.host,
                user=self.username,
                pwd=self.password,
                sslContext=context,
            )
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
            snap_info = {'name': snapshot.name, 'timestamp_seconds': snap_timestamp}
            snapshot_data.append(snap_info)
            snapshot_data = snapshot_data + self._vmware_full_snapshots_list(
                snapshot.childSnapshotList)
        return snapshot_data

    def _vmware_get_datastores(self, content, ds_metrics, inventory):
        """
        Get Datastore information
        """
        log("Starting datastore metrics collection")
        datastores = self._vmware_get_obj(content, [vim.Datastore])
        for datastore in datastores:
            # ds.RefreshDatastoreStorageInfo()
            summary = datastore.summary
            ds_name = summary.name
            dc_name = inventory[ds_name]['dc']
            ds_cluster = inventory[ds_name]['ds_cluster']

            self.thread_it(
                self._vmware_get_datastore_metrics,
                [datastore, dc_name, ds_cluster, ds_metrics, summary]
            )
        log("Finished datastore metrics collection")

    def _vmware_get_datastore_metrics(self, datastore, dc_name, ds_cluster, ds_metrics, summary):
        """
        Get datastore metrics
        """
        metadata = [summary.name, dc_name, ds_cluster]

        ds_capacity = float(summary.capacity)
        ds_freespace = float(summary.freeSpace)
        ds_uncommitted = float(summary.uncommitted) if summary.uncommitted else 0
        ds_provisioned = ds_capacity - ds_freespace + ds_uncommitted

        ds_metrics['vmware_datastore_capacity_size'].add_metric(metadata, ds_capacity)
        ds_metrics['vmware_datastore_freespace_size'].add_metric(metadata, ds_freespace)
        ds_metrics['vmware_datastore_uncommited_size'].add_metric(metadata, ds_uncommitted)
        ds_metrics['vmware_datastore_provisoned_size'].add_metric(metadata, ds_provisioned)
        ds_metrics['vmware_datastore_hosts'].add_metric(metadata, len(datastore.host))
        ds_metrics['vmware_datastore_vms'].add_metric(metadata, len(datastore.vm))
        ds_metrics['vmware_datastore_maintenance_mode'].add_metric(
            metadata + [summary.maintenanceMode or 'normal'],
            1)
        ds_metrics['vmware_datastore_type'].add_metric(metadata + [summary.type or 'normal'], 1)
        ds_metrics['vmware_datastore_accessible'].add_metric(metadata, summary.accessible*1)

    def _vmware_get_vm_perf_manager_metrics(self, content, counter_info, virtual_machines, vm_metrics, inventory):
        log('START: _vmware_get_vm_perf_manager_metrics')
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

        metrics = []
        metric_names = {}
        for perf_metric in perf_list:
            perf_metric_name = 'vmware_vm_' + perf_metric.replace('.', '_')
            counter_key = counter_info[perf_metric]
            metrics.append(vim.PerformanceManager.MetricId(
                counterId=counter_key,
                instance=''
            ))
            metric_names[counter_key] = perf_metric_name

        specs = []
        for vm in virtual_machines:
            # summary = vm.summary
            # if summary.runtime.powerState != 'poweredOn':
            #     continue
            specs.append(vim.PerformanceManager.QuerySpec(
                maxSample=1,
                entity=vm,
                metricId=metrics,
                intervalId=20
            ))

        log('START: _vmware_get_vm_perf_manager_metrics: QUERY')
        result = content.perfManager.QueryStats(querySpec=specs)
        log('FIN: _vmware_get_vm_perf_manager_metrics: QUERY')

        for ent in result:
            for metric in ent.value:
                vm_metrics[metric_names[metric.id.counterId]].add_metric(
                    self._labels[ent.entity._moId],
                    float(sum(metric.value)),
                )
        log('FIN: _vmware_get_vm_perf_manager_metrics')

    def _vmware_get_vmguests(self, content, vmguest_metrics, inventory):
        """
        Get VM Guest information
        """

        virtual_machines = self._vmware_get_obj(content, [vim.VirtualMachine])

        log("Total Virtual Machines: {0}".format(len(virtual_machines)))
        for virtual_machine in virtual_machines:
            self.thread_it(
                self._vmware_get_vm_metrics,
                [content, virtual_machine, vmguest_metrics, inventory]
            )
        return virtual_machines

    def _vmware_get_vm_metrics(self, content, virtual_machine, metrics, inventory):
        """
        Get VM Guest Metrics
        """
        summary = virtual_machine.summary

        vm_metadata = list(self._vmware_vm_metadata(inventory, virtual_machine, summary))
        self._labels[virtual_machine._moId] = vm_metadata

        if self.collect_only['vms'] is True:
            vm_power_state = 1 if summary.runtime.powerState == 'poweredOn' else 0
            vm_num_cpu = summary.config.numCpu

            metrics['vmware_vm_power_state'].add_metric(vm_metadata, vm_power_state)
            metrics['vmware_vm_num_cpu'].add_metric(vm_metadata, vm_num_cpu)

            # Get metrics for poweredOn vms only
            if vm_power_state:
                if summary.runtime.bootTime:
                    metrics['vmware_vm_boot_timestamp_seconds'].add_metric(
                        vm_metadata,
                        self._to_epoch(summary.runtime.bootTime)
                    )

        if self.collect_only['vmguests'] is True:
            # gather disk metrics
            if len(virtual_machine.guest.disk) > 0:
                for disk in virtual_machine.guest.disk:
                    metrics['vmware_vm_guest_disk_free'].add_metric(
                        vm_metadata + [disk.diskPath], disk.freeSpace)
                    metrics['vmware_vm_guest_disk_capacity'].add_metric(
                        vm_metadata + [disk.diskPath], disk.capacity)

        if self.collect_only['snapshots'] is True and virtual_machine.snapshot is not None:
            snapshots = self._vmware_full_snapshots_list(virtual_machine.snapshot.rootSnapshotList)

            metrics['vmware_vm_snapshots'].add_metric(
                vm_metadata,
                len(snapshots),
            )

            for snapshot in snapshots:
                metrics['vmware_vm_snapshot_timestamp_seconds'].add_metric(
                    vm_metadata + [snapshot['name']],
                    snapshot['timestamp_seconds'],
                )

    def _vmware_get_hosts(self, content, host_metrics, inventory):
        """
        Get Host (ESXi) information
        """
        log("Starting host metrics collection")
        hosts = self._vmware_get_obj(content, [vim.HostSystem])
        for host in hosts:
            summary = host.summary
            host_name, host_dc_name, host_cluster_name = self._vmware_host_metadata(inventory, host)
            host_metadata = [host_name, host_dc_name, host_cluster_name]

            # Power state
            power_state = 1 if summary.runtime.powerState == 'poweredOn' else 0
            host_metrics['vmware_host_power_state'].add_metric(host_metadata,
                                                               power_state)

            if power_state:
                self.thread_it(
                    self._vmware_get_host_metrics,
                    [host_name, host_dc_name, host_cluster_name, host_metrics, summary]
                )
        log("Finished host metrics collection")

    def _vmware_get_host_metrics(self, host_name, host_dc_name, host_cluster_name, host_metrics, summary):
        """
        Get Host Metrics
        """

        labels = [host_name, host_dc_name, host_cluster_name]

        if summary.runtime.bootTime:
            # Host uptime
            host_metrics['vmware_host_boot_timestamp_seconds'].add_metric(labels,
                                                                          self._to_epoch(
                                                                              summary.runtime.bootTime)
                                                                          )

            # Host connection state (connected, disconnected, notResponding)
            metric_labels = labels
            metric_labels.append(summary.runtime.connectionState)
            host_metrics['vmware_host_connection_state'].add_metric(metric_labels, 1)

            # Host in maintenance mode?
            host_metrics['vmware_host_maintenance_mode'].add_metric(labels,
                                                                    summary.runtime.inMaintenanceMode*1)

        # CPU Usage (in Mhz)
        host_metrics['vmware_host_cpu_usage'].add_metric(labels,
                                                         summary.quickStats.overallCpuUsage)
        cpu_core_num = summary.hardware.numCpuCores
        cpu_total = summary.hardware.cpuMhz * cpu_core_num
        host_metrics['vmware_host_cpu_max'].add_metric(labels,
                                                       cpu_total)

        # Memory Usage (in MB)
        host_metrics['vmware_host_memory_usage'].add_metric(labels,
                                                            summary.quickStats.overallMemoryUsage)
        host_metrics['vmware_host_memory_max'].add_metric(labels,
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
                        host_name = host.summary.config.name.rstrip('.')
                        host_inventory[host_name] = {}
                        host_inventory[host_name]['dc'] = dc.name
                        host_inventory[host_name]['cluster'] = folder.name
                else:  # Unclustered host
                    host_name = folder.name.rstrip('.')
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
        if not summary:
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
                    vmguests: True
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
            self.config['default']['collect_only']['vmguests'] = os.environ.get('VSPHERE_COLLECT_VMGUESTS', True)
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
            log(b"Uri not found: " + request.uri)
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
        if section not in self.config.keys():
            log("{} is not a valid section, using default".format(section))
            section = 'default'

        if self.config[section].get('vsphere_host') and self.config[section].get('vsphere_host') != "None":
            vsphere_host = self.config[section].get('vsphere_host')
        elif request.args.get(b'target', [None])[0]:
            vsphere_host = request.args.get(b'target', [None])[0].decode('utf-8')
        elif request.args.get(b'vsphere_host', [None])[0]:
            vsphere_host = request.args.get(b'vsphere_host')[0].decode('utf-8')
        else:
            request.setResponseCode(500)
            log("No vsphere_host or target defined")
            request.write(b'No vsphere_host or target defined!\n')
            request.finish()
            return

        registry = CollectorRegistry()
        registry.register(VmwareCollector(
            vsphere_host,
            self.config[section]['vsphere_user'],
            self.config[section]['vsphere_password'],
            self.config[section]['collect_only'],
            self.config[section]['ignore_ssl'],
        ))
        output = generate_latest(registry)

        request.write(output)
        request.finish()


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
