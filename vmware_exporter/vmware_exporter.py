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
            """.format(os.environ.get('VSPHERE_HOST'),
                       os.environ.get('VSPHERE_USER'),
                       os.environ.get('VSPHERE_PASSWORD'),
                       os.environ.get('VSPHERE_IGNORE_SSL', False)
                       )
            self.config = yaml.load(config_data)
            self.config['default']['collect_only']['hosts'] = os.environ.get('VSPHERE_COLLECT_HOSTS', True)
            self.config['default']['collect_only']['datastores'] = os.environ.get('VSPHERE_COLLECT_DATASTORES', True)
            self.config['default']['collect_only']['vms'] = os.environ.get('VSPHERE_COLLECT_VMS', True)

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
        if not request.args.get('vsphere_host', [None])[0] and not self.config[section].get('vsphere_host'):
            request.setResponseCode(500)
            log("No vsphere_host defined")
            request.write('No vsphere_host defined!\n')
            request.finish()
        if self.config[section].get('vsphere_host'):
            vsphere_host = self.config[section].get('vsphere_host')
        else:
            vsphere_host = request.args.get('vsphere_host')[0]
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
        metric_list = {}
        metric_list['vms'] = {
            'vmware_vm_power_state': GaugeMetricFamily(
                'vmware_vm_power_state',
                'VMWare VM Power state (On / Off)',
                labels=['vm_name', 'host_name']),
            'vmware_vm_boot_timestamp_seconds': GaugeMetricFamily(
                'vmware_vm_boot_timestamp_seconds',
                'VMWare VM boot time in seconds',
                labels=['vm_name', 'host_name']),
            'vmware_vm_snapshots': GaugeMetricFamily(
                'vmware_vm_snapshots',
                'VMWare current number of existing snapshots',
                labels=['vm_name']),
            'vmware_vm_snapshot_timestamp_seconds': GaugeMetricFamily(
                'vmware_vm_snapshot_timestamp_seconds',
                'VMWare Snapshot creation time in seconds',
                labels=['vm_name', 'vm_snapshot_name']),
            'vmware_vm_num_cpu': GaugeMetricFamily(
                'vmware_vm_num_cpu',
                'VMWare Number of processors in the virtual machine',
                labels=['vm_name', 'host_name'])
            }
        metric_list['datastores'] = {
            'vmware_datastore_capacity_size': GaugeMetricFamily(
                'vmware_datastore_capacity_size',
                'VMWare Datasore capacity in bytes',
                labels=['ds_name']),
            'vmware_datastore_freespace_size': GaugeMetricFamily(
                'vmware_datastore_freespace_size',
                'VMWare Datastore freespace in bytes',
                labels=['ds_name']),
            'vmware_datastore_uncommited_size': GaugeMetricFamily(
                'vmware_datastore_uncommited_size',
                'VMWare Datastore uncommitted in bytes',
                labels=['ds_name']),
            'vmware_datastore_provisoned_size': GaugeMetricFamily(
                'vmware_datastore_provisoned_size',
                'VMWare Datastore provisoned in bytes',
                labels=['ds_name']),
            'vmware_datastore_hosts': GaugeMetricFamily(
                'vmware_datastore_hosts',
                'VMWare Hosts number using this datastore',
                labels=['ds_name']),
            'vmware_datastore_vms': GaugeMetricFamily(
                'vmware_datastore_vms',
                'VMWare Virtual Machines number using this datastore',
                labels=['ds_name'])
            }
        metric_list['hosts'] = {
            'vmware_host_power_state': GaugeMetricFamily(
                'vmware_host_power_state',
                'VMWare Host Power state (On / Off)',
                labels=['host_name']),
            'vmware_host_boot_timestamp_seconds': GaugeMetricFamily(
                'vmware_host_boot_timestamp_seconds',
                'VMWare Host boot time in seconds',
                labels=['host_name']),
            'vmware_host_cpu_usage': GaugeMetricFamily(
                'vmware_host_cpu_usage',
                'VMWare Host CPU usage in Mhz',
                labels=['host_name']),
            'vmware_host_cpu_max': GaugeMetricFamily(
                'vmware_host_cpu_max',
                'VMWare Host CPU max availability in Mhz',
                labels=['host_name']),
            'vmware_host_memory_usage': GaugeMetricFamily(
                'vmware_host_memory_usage',
                'VMWare Host Memory usage in Mbytes',
                labels=['host_name']),
            'vmware_host_memory_max': GaugeMetricFamily(
                'vmware_host_memory_max',
                'VMWare Host Memory Max availability in Mbytes',
                labels=['host_name']),
            }

        metrics = {}
        for key, value in self.config[section]['collect_only'].items():
            if value is True:
                metrics.update(metric_list[key])

        log("Start collecting vcenter metrics for {0}".format(vsphere_host))

        self.vmware_connection = self._vmware_connect(vsphere_host, section)
        if not self.vmware_connection:
            log("Cannot connect to vmware")
            return

        content = self.vmware_connection.RetrieveContent()

        if self.config[section]['collect_only']['vms'] is True:
            # Get performance metrics counter information
            counter_info = self._vmware_perf_metrics(content)

            # Fill VM Informations
            log("Starting VM performance metric collection")
            self._vmware_get_vms(content, metrics, counter_info)
            log("Finish starting vm performance vm collection")

            # Fill Snapshots (count and age)
            log("Starting VM snapshot metric collection")
            vm_counts, vm_ages = self._vmware_get_snapshots(content)
            for v in vm_counts:
                metrics['vmware_vm_snapshots'].add_metric([v['vm_name']], v['snapshot_count'])
            for vm_age in vm_ages:
                for v in vm_age:
                    metrics['vmware_vm_snapshot_timestamp_seconds'].add_metric([v['vm_name'],
                                                                                v['vm_snapshot_name']],
                                                                               v['vm_snapshot_timestamp_seconds']
                                                                               )
            log("Finished VM snapshot metric collection")

        # Fill Datastore
        if self.config[section]['collect_only']['datastores'] is True:
            self._vmware_get_datastores(content, metrics)

        # Fill Hosts Informations
        if self.config[section]['collect_only']['hosts'] is True:
            self._vmware_get_hosts(content, metrics)

        log("Stop collecting vcenter metrics for {0}".format(vsphere_host))
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
            vmware_connect = connect.Connect(vsphere_host, 443,
                                             vsphere_user,
                                             vsphere_password,
                                             sslContext=context
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
            snap_info = {'vm_snapshot_name': snapshot.name, 'vm_snapshot_timestamp_seconds': snap_timestamp}
            snapshot_data.append(snap_info)
            snapshot_data = snapshot_data + self._vmware_full_snapshots_list(
                snapshot.childSnapshotList)
        return snapshot_data

    def _vmware_get_snapshot_details(self, snapshots_count_table, snapshots_age_table, virtual_machine):
        """
        Gathers snapshot details
        """
        snapshot_paths = self._vmware_full_snapshots_list(virtual_machine.snapshot.rootSnapshotList)
        for snapshot_path in snapshot_paths:
            snapshot_path['vm_name'] = virtual_machine.name
        # Add Snapshot count per VM
        snapshot_count = len(snapshot_paths)
        snapshot_count_info = {
            'vm_name': virtual_machine.name,
            'snapshot_count': snapshot_count
        }
        snapshots_count_table.append(snapshot_count_info)
        snapshots_age_table.append(snapshot_paths)

    def _vmware_get_snapshots(self, content):
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
                                        [snapshots_count_table, snapshots_age_table, virtual_machine])
        return snapshots_count_table, snapshots_age_table

    def _vmware_get_datastores(self, content, ds_metrics):
        """
        Get Datastore information
        """
        log("Starting datastore metric collection")
        datastores = self._vmware_get_obj(content, [vim.Datastore])
        for datastore in datastores:
            # ds.RefreshDatastoreStorageInfo()
            summary = datastore.summary
            self.threader.thread_it(self._vmware_get_datastore_metrics, [datastore, ds_metrics, summary])
        log("Finished datastore metric collection")

    def _vmware_get_datastore_metrics(self, datastore, ds_metrics, summary):
        """
        Get datastore metrics
        """
        ds_capacity = summary.capacity
        ds_freespace = summary.freeSpace
        ds_uncommitted = summary.uncommitted if summary.uncommitted else 0
        ds_provisioned = ds_capacity - ds_freespace + ds_uncommitted

        ds_metrics['vmware_datastore_capacity_size'].add_metric([summary.name], ds_capacity)
        ds_metrics['vmware_datastore_freespace_size'].add_metric([summary.name], ds_freespace)
        ds_metrics['vmware_datastore_uncommited_size'].add_metric([summary.name], ds_uncommitted)
        ds_metrics['vmware_datastore_provisoned_size'].add_metric([summary.name], ds_provisioned)
        ds_metrics['vmware_datastore_hosts'].add_metric([summary.name], len(datastore.host))
        ds_metrics['vmware_datastore_vms'].add_metric([summary.name], len(datastore.vm))

    def _vmware_get_vms(self, content, vm_metrics, counter_info):
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
                labels=['vm_name', 'host_name'])

        virtual_machines = self._vmware_get_obj(content, [vim.VirtualMachine])
        log("Total Virtual Machines: {0}".format(len(virtual_machines)))
        for virtual_machine in virtual_machines:
            self.threader.thread_it(self._vmware_get_vm_perf_metrics,
                                    [content, counter_info, perf_list, virtual_machine, vm_metrics])

    def _vmware_get_vm_perf_metrics(self, content, counter_info, perf_list, virtual_machine, vm_metrics):
        """
        Loops over metrics in perf_list on vm
        """
        # DEBUG ME: log("Starting VM: " + vm.name)
        summary = virtual_machine.summary

        power_state = 1 if summary.runtime.powerState == 'poweredOn' else 0
        num_cpu = summary.config.numCpu
        vm_host = summary.runtime.host
        vm_host_name = vm_host.name
        vm_metrics['vmware_vm_power_state'].add_metric([virtual_machine.name, vm_host_name], power_state)
        vm_metrics['vmware_vm_num_cpu'].add_metric([virtual_machine.name, vm_host_name], num_cpu)

        # Get metrics for poweredOn vms only
        if power_state:
            if summary.runtime.bootTime:
                vm_metrics['vmware_vm_boot_timestamp_seconds'].add_metric([virtual_machine.name,
                                                                           vm_host_name],
                                                                          self._to_epoch(summary.runtime.bootTime))

            for p in perf_list:
                self.threader.thread_it(self._vmware_get_vm_perf_metric,
                                        [content, counter_info, p, virtual_machine, vm_host_name, vm_metrics])

        # Debug Me. log("Finished VM: " + vm.name)

    def _vmware_get_vm_perf_metric(self, content, counter_info, perf_metric, virtual_machine, vm_host_name, vm_metrics):
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
            vm_metrics[perf_metric_name].add_metric([virtual_machine.name, vm_host_name],
                                                    float(sum(result[0].value[0].value)))
        except:  # noqa: E722
            log("Error, cannot get vm metrics {0} for {1}".format(perf_metric_name,
                                                                  virtual_machine.name))

    def _vmware_get_hosts(self, content, host_metrics):
        """
        Get Host (ESXi) information
        """
        log("Starting host metric collection")
        hosts = self._vmware_get_obj(content, [vim.HostSystem])
        for host in hosts:
            summary = host.summary
            # Power state
            power_state = 1 if summary.runtime.powerState == 'poweredOn' else 0
            host_metrics['vmware_host_power_state'].add_metric([host.name], power_state)

            if power_state:
                self.threader.thread_it(self._vmware_get_host_metrics, [host, host_metrics, summary])
        log("Finished host metric collection")

    def _vmware_get_host_metrics(self, host, host_metrics, summary):
        """
        Get Host Metrics
        """
        # Uptime
        if summary.runtime.bootTime:
            host_metrics['vmware_host_boot_timestamp_seconds'].add_metric([host.name],
                                                                          self._to_epoch(
                                                                              summary.runtime.bootTime)
                                                                          )
        # CPU Usage (in Mhz)
        host_metrics['vmware_host_cpu_usage'].add_metric([host.name], summary.quickStats.overallCpuUsage)
        cpu_core_num = summary.hardware.numCpuCores
        cpu_total = summary.hardware.cpuMhz * cpu_core_num
        host_metrics['vmware_host_cpu_max'].add_metric([host.name], cpu_total)

        # Memory Usage (in MB)
        host_metrics['vmware_host_memory_usage'].add_metric([host.name], summary.quickStats.overallMemoryUsage)
        host_metrics['vmware_host_memory_max'].add_metric([host.name], float(summary.hardware.memorySize) / 1024 / 1024)


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
