#!/usr/bin/env python
# -*- python -*-
# -*- coding: utf-8 -*-
"""
Handles collection of metrics for vmware.
"""

from __future__ import print_function
import datetime

# Generic imports
import argparse
import os
import ssl
import sys
import traceback
import pytz
import logging

from yamlconfig import YamlConfig

# Twisted
from twisted.web.server import Site, NOT_DONE_YET
from twisted.web.resource import Resource
from twisted.internet import reactor, endpoints, defer, threads

# VMWare specific imports
from pyVmomi import vim, vmodl
from pyVim import connect

# Prometheus specific imports
from prometheus_client.core import GaugeMetricFamily
from prometheus_client import CollectorRegistry, generate_latest

from .helpers import batch_fetch_properties, get_bool_env
from .defer import parallelize, run_once_property


class VmwareCollector():

    def __init__(self, host, username, password, collect_only, ignore_ssl=False):
        self.host = host
        self.username = username
        self.password = password
        self.ignore_ssl = ignore_ssl
        self.collect_only = collect_only

    def _create_metric_containers(self):
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
            'vmware_vm_memory_max': GaugeMetricFamily(
                'vmware_vm_memory_max',
                'VMWare VM Memory Max availability in Mbytes',
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
            'vmware_vm_guest_tools_running_status': GaugeMetricFamily(
                'vmware_vm_guest_tools_running_status',
                'VM tools running status',
                labels=['vm_name', 'host_name', 'dc_name', 'cluster_name', 'tools_status', ]),
            'vmware_vm_guest_tools_version': GaugeMetricFamily(
                'vmware_vm_guest_tools_version',
                'VM tools version',
                labels=['vm_name', 'host_name', 'dc_name', 'cluster_name', 'tools_version', ]),
            'vmware_vm_guest_tools_version_status': GaugeMetricFamily(
                'vmware_vm_guest_tools_version_status',
                'VM tools version status',
                labels=['vm_name', 'host_name', 'dc_name', 'cluster_name', 'tools_version_status', ]),
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
            'vmware_host_num_cpu': GaugeMetricFamily(
                'vmware_host_num_cpu',
                'VMWare Number of processors in the Host',
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

        return metrics

    @defer.inlineCallbacks
    def collect(self):
        """ collects metrics """
        vsphere_host = self.host

        metrics = self._create_metric_containers()

        logging.info("Start collecting metrics from {vsphere_host}".format(vsphere_host=vsphere_host))

        self._labels = {}

        collect_only = self.collect_only

        tasks = []

        # Collect vm / snahpshot / vmguest metrics
        if collect_only['vmguests'] is True or collect_only['vms'] is True or collect_only['snapshots'] is True:
            tasks.append(self._vmware_get_vms(metrics))

        if collect_only['vms'] is True:
            tasks.append(self._vmware_get_vm_perf_manager_metrics(metrics))

        # Collect Datastore metrics
        if collect_only['datastores'] is True:
            tasks.append(self._vmware_get_datastores(metrics,))

        if collect_only['hosts'] is True:
            tasks.append(self._vmware_get_hosts(metrics))

        yield parallelize(*tasks)

        yield self._vmware_disconnect()

        logging.info("Finished collecting metrics from {vsphere_host}".format(vsphere_host=vsphere_host))

        return list(metrics.values())   # noqa: F705

    def _to_epoch(self, my_date):
        """ convert to epoch time """
        return (my_date - datetime.datetime(1970, 1, 1, tzinfo=pytz.utc)).total_seconds()

    @run_once_property
    @defer.inlineCallbacks
    def connection(self):
        """
        Connect to Vcenter and get connection
        """
        context = None
        if self.ignore_ssl:
            context = ssl._create_unverified_context()

        try:
            vmware_connect = yield threads.deferToThread(
                connect.SmartConnect,
                host=self.host,
                user=self.username,
                pwd=self.password,
                sslContext=context,
            )
            return vmware_connect

        except vmodl.MethodFault as error:
            logging.error("Caught vmodl fault: {error}".format(error=error.msg))
            return None

    @run_once_property
    @defer.inlineCallbacks
    def content(self):
        logging.info("Retrieving service instance content")
        connection = yield self.connection
        content = yield threads.deferToThread(
            connection.RetrieveContent
        )

        logging.info("Retrieved service instance content")
        return content

    @defer.inlineCallbacks
    def batch_fetch_properties(self, objtype, properties):
        content = yield self.content
        batch = yield threads.deferToThread(
            batch_fetch_properties,
            content,
            objtype,
            properties,
        )
        return batch

    @run_once_property
    @defer.inlineCallbacks
    def datastore_inventory(self):
        logging.info("Fetching vim.Datastore inventory")
        start = datetime.datetime.utcnow()
        properties = [
            'name',
            'summary.capacity',
            'summary.freeSpace',
            'summary.uncommitted',
            'summary.maintenanceMode',
            'summary.type',
            'summary.accessible',
            'host',
            'vm',
        ]

        datastores = yield self.batch_fetch_properties(
            vim.Datastore,
            properties
        )
        fetch_time = datetime.datetime.utcnow() - start
        logging.info("Fetched vim.Datastore inventory ({fetch_time})".format(fetch_time=fetch_time))
        return datastores

    @run_once_property
    @defer.inlineCallbacks
    def host_system_inventory(self):
        logging.info("Fetching vim.HostSystem inventory")
        start = datetime.datetime.utcnow()
        properties = [
            'name',
            'parent',
            'summary.hardware.numCpuCores',
            'summary.hardware.cpuMhz',
            'summary.hardware.memorySize',
            'runtime.powerState',
            'runtime.bootTime',
            'runtime.connectionState',
            'runtime.inMaintenanceMode',
            'summary.quickStats.overallCpuUsage',
            'summary.quickStats.overallMemoryUsage',
        ]

        host_systems = yield self.batch_fetch_properties(
            vim.HostSystem,
            properties,
        )
        fetch_time = datetime.datetime.utcnow() - start
        logging.info("Fetched vim.HostSystem inventory ({fetch_time})".format(fetch_time=fetch_time))
        return host_systems

    @run_once_property
    @defer.inlineCallbacks
    def vm_inventory(self):
        logging.info("Fetching vim.VirtualMachine inventory")
        start = datetime.datetime.utcnow()
        properties = [
            'name',
            'runtime.host',
            'parent',
        ]

        if self.collect_only['vms'] is True:
            properties.extend([
                'runtime.powerState',
                'runtime.bootTime',
                'summary.config.numCpu',
                'summary.config.memorySizeMB',
            ])

        if self.collect_only['vmguests'] is True:
            properties.extend([
                'guest.disk',
                'guest.toolsStatus',
                'guest.toolsVersion',
                'guest.toolsVersionStatus2',
            ])

        if self.collect_only['snapshots'] is True:
            properties.append('snapshot')

        virtual_machines = yield self.batch_fetch_properties(
            vim.VirtualMachine,
            properties,
        )
        fetch_time = datetime.datetime.utcnow() - start
        logging.info("Fetched vim.VirtualMachine inventory ({fetch_time})".format(fetch_time=fetch_time))
        return virtual_machines

    @run_once_property
    @defer.inlineCallbacks
    def datacenter_inventory(self):
        content = yield self.content
        # FIXME: It's unclear if this is operating on data already fetched in
        # content or if this is doing stealth HTTP requests
        # Right now we assume it does stealth lookups
        datacenters = yield threads.deferToThread(lambda: content.rootFolder.childEntity)
        return datacenters

    @run_once_property
    @defer.inlineCallbacks
    def datastore_labels(self):

        def _collect(node, level=1, dc=None, storagePod=""):
            inventory = {}
            if isinstance(node, vim.Folder) and not isinstance(node, vim.StoragePod):
                logging.debug("[Folder    ] {level} {name}".format(name=node.name, level=('-' * level).ljust(7)))
                for child in node.childEntity:
                    inventory.update(_collect(child, level + 1, dc))
            elif isinstance(node, vim.Datacenter):
                logging.debug("[Datacenter] {level} {name}".format(name=node.name, level=('-' * level).ljust(7)))
                inventory.update(_collect(node.datastoreFolder, level + 1, node.name))
            elif isinstance(node, vim.Folder) and isinstance(node, vim.StoragePod):
                logging.debug("[StoragePod] {level} {name}".format(name=node.name, level=('-' * level).ljust(7)))
                for child in node.childEntity:
                    inventory.update(_collect(child, level + 1, dc, node.name))
            elif isinstance(node, vim.Datastore):
                logging.debug("[Datastore ] {level} {name}".format(name=node.name, level=('-' * level).ljust(7)))
                inventory[node.name] = [node.name, dc, storagePod]
            else:
                logging.debug("[?         ] {level} {node}".format(node=node, level=('-' * level).ljust(7)))
            return inventory

        labels = {}
        dcs = yield self.datacenter_inventory
        for dc in dcs:
            result = yield threads.deferToThread(lambda: _collect(dc))
            labels.update(result)
        return labels

    @run_once_property
    @defer.inlineCallbacks
    def host_labels(self):

        def _collect(node, level=1, dc=None, folder=None):
            inventory = {}
            if isinstance(node, vim.Folder) and not isinstance(node, vim.StoragePod):
                logging.debug("[Folder    ] {level} {name}".format(level=('-' * level).ljust(7), name=node.name))
                for child in node.childEntity:
                    inventory.update(_collect(child, level + 1, dc))
            elif isinstance(node, vim.Datacenter):
                logging.debug("[Datacenter] {level} {name}".format(level=('-' * level).ljust(7), name=node.name))
                inventory.update(_collect(node.hostFolder, level + 1, node.name))
            elif isinstance(node, vim.ComputeResource):
                logging.debug("[ComputeRes] {level} {name}".format(level=('-' * level).ljust(7), name=node.name))
                for host in node.host:
                    inventory.update(_collect(host, level + 1, dc, node))
            elif isinstance(node, vim.HostSystem):
                logging.debug("[HostSystem] {level} {name}".format(level=('-' * level).ljust(7), name=node.name))
                inventory[node._moId] = [
                    node.summary.config.name.rstrip('.'),
                    dc,
                    folder.name if isinstance(folder, vim.ClusterComputeResource) else ''
                    ]
            else:
                logging.debug("[?         ] {level} {node}".format(level=('-' * level).ljust(7), node=node))
            return inventory

        labels = {}
        dcs = yield self.datacenter_inventory
        for dc in dcs:
            result = yield threads.deferToThread(lambda: _collect(dc))
            labels.update(result)
        return labels

    @run_once_property
    @defer.inlineCallbacks
    def vm_labels(self):
        virtual_machines, host_labels = yield parallelize(self.vm_inventory, self.host_labels)

        labels = {}
        for moid, row in virtual_machines.items():

            host_moid = None
            if 'runtime.host' in row:
                host_moid = row['runtime.host']._moId

            labels[moid] = [row['name']]

            if host_moid in host_labels:
                labels[moid] = labels[moid] + host_labels[host_moid]

        return labels

    @run_once_property
    @defer.inlineCallbacks
    def counter_ids(self):
        """
        create a mapping from performance stats to their counterIDs
        counter_info: [performance stat => counterId]
        performance stat example: cpu.usagemhz.LATEST
        """
        content = yield self.content
        counter_info = {}
        for counter in content.perfManager.perfCounter:
            prefix = counter.groupInfo.key
            counter_full = "{}.{}.{}".format(prefix, counter.nameInfo.key, counter.rollupType)
            counter_info[counter_full] = counter.key
        return counter_info

    @defer.inlineCallbacks
    def _vmware_disconnect(self):
        """
        Disconnect from Vcenter
        """
        connection = yield self.connection
        yield threads.deferToThread(
            connect.Disconnect,
            connection,
        )
        del self.connection

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

    @defer.inlineCallbacks
    def _vmware_get_datastores(self, ds_metrics):
        """
        Get Datastore information
        """

        results, datastore_labels = yield parallelize(self.datastore_inventory, self.datastore_labels)

        for datastore_id, datastore in results.items():
            try:
                name = datastore['name']
                labels = datastore_labels[name]
            except KeyError as e:
                logging.info(
                    "Key error, unable to register datastore {error}, datastores are {datastore_labels}".format(
                        error=e, datastore_labels=datastore_labels
                    )
                )
                continue

            ds_capacity = float(datastore.get('summary.capacity', 0))
            ds_freespace = float(datastore.get('summary.freeSpace', 0))
            ds_uncommitted = float(datastore.get('summary.uncommitted', 0))
            ds_provisioned = ds_capacity - ds_freespace + ds_uncommitted

            ds_metrics['vmware_datastore_capacity_size'].add_metric(labels, ds_capacity)
            ds_metrics['vmware_datastore_freespace_size'].add_metric(labels, ds_freespace)
            ds_metrics['vmware_datastore_uncommited_size'].add_metric(labels, ds_uncommitted)
            ds_metrics['vmware_datastore_provisoned_size'].add_metric(labels, ds_provisioned)

            ds_metrics['vmware_datastore_hosts'].add_metric(labels, len(datastore.get('host', [])))
            ds_metrics['vmware_datastore_vms'].add_metric(labels, len(datastore.get('vm', [])))

            ds_metrics['vmware_datastore_maintenance_mode'].add_metric(
                labels + [datastore.get('summary.maintenanceMode', 'unknown')],
                1
            )

            ds_metrics['vmware_datastore_type'].add_metric(
                labels + [datastore.get('summary.type', 'normal')],
                1
            )

            if 'summary.accessible' in datastore:
                ds_metrics['vmware_datastore_accessible'].add_metric(
                    labels,
                    datastore['summary.accessible'] * 1,
                )

        return results

    @defer.inlineCallbacks
    def _vmware_get_vm_perf_manager_metrics(self, vm_metrics):
        logging.info('START: _vmware_get_vm_perf_manager_metrics')

        virtual_machines, counter_info = yield parallelize(self.vm_inventory, self.counter_ids)

        # List of performance counter we want
        perf_list = [
            'cpu.ready.summation',
            'cpu.maxlimited.summation',
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
        for vm in virtual_machines.values():
            if vm.get('runtime.powerState') != 'poweredOn':
                continue
            specs.append(vim.PerformanceManager.QuerySpec(
                maxSample=1,
                entity=vm['obj'],
                metricId=metrics,
                intervalId=20
            ))

        content = yield self.content

        if len(specs) > 0:
            results, labels = yield parallelize(
                threads.deferToThread(content.perfManager.QueryStats, querySpec=specs),
                self.vm_labels,
            )

            for ent in results:
                for metric in ent.value:
                    vm_metrics[metric_names[metric.id.counterId]].add_metric(
                        labels[ent.entity._moId],
                        float(sum(metric.value)),
                     )

        logging.info('FIN: _vmware_get_vm_perf_manager_metrics')

    @defer.inlineCallbacks
    def _vmware_get_vms(self, metrics):
        """
        Get VM information
        """
        logging.info("Starting vm metrics collection")

        virtual_machines, vm_labels = yield parallelize(self.vm_inventory, self.vm_labels)

        for moid, row in virtual_machines.items():
            # Ignore vm if field "runtime.host" does not exist
            # It will happen during a VM is cloning
            if 'runtime.host' not in row:
                continue

            labels = vm_labels[moid]
            labels_cnt = len(labels)

            if labels_cnt < 4:
                logging.info("Only ${cnt}/4 labels (vm, host, dc, cluster) found, filling n/a".format(cnt=labels_cnt))

            for i in range(labels_cnt, 4):
                labels.append('n/a')

            if 'runtime.powerState' in row:
                power_state = 1 if row['runtime.powerState'] == 'poweredOn' else 0
                metrics['vmware_vm_power_state'].add_metric(labels, power_state)

                if power_state and row.get('runtime.bootTime'):
                    metrics['vmware_vm_boot_timestamp_seconds'].add_metric(
                        labels,
                        self._to_epoch(row['runtime.bootTime'])
                    )

            if 'summary.config.numCpu' in row:
                metrics['vmware_vm_num_cpu'].add_metric(labels, row['summary.config.numCpu'])

            if 'summary.config.memorySizeMB' in row:
                metrics['vmware_vm_memory_max'].add_metric(labels, row['summary.config.memorySizeMB'])

            if 'guest.disk' in row and len(row['guest.disk']) > 0:
                for disk in row['guest.disk']:
                    metrics['vmware_vm_guest_disk_free'].add_metric(
                        labels + [disk.diskPath], disk.freeSpace
                    )
                    metrics['vmware_vm_guest_disk_capacity'].add_metric(
                        labels + [disk.diskPath], disk.capacity
                    )

            if 'guest.toolsStatus' in row:
                metrics['vmware_vm_guest_tools_running_status'].add_metric(
                    labels + [row['guest.toolsStatus']], 1
                )

            if 'guest.toolsVersion' in row:
                metrics['vmware_vm_guest_tools_version'].add_metric(
                    labels + [row['guest.toolsVersion']], 1
                )

            if 'guest.toolsVersionStatus2' in row:
                metrics['vmware_vm_guest_tools_version_status'].add_metric(
                    labels + [row['guest.toolsVersionStatus2']], 1
                )

            if 'snapshot' in row:
                snapshots = self._vmware_full_snapshots_list(row['snapshot'].rootSnapshotList)

                metrics['vmware_vm_snapshots'].add_metric(
                    labels,
                    len(snapshots),
                )

                for snapshot in snapshots:
                    metrics['vmware_vm_snapshot_timestamp_seconds'].add_metric(
                        labels + [snapshot['name']],
                        snapshot['timestamp_seconds'],
                    )

        logging.info("Finished vm metrics collection")

    @defer.inlineCallbacks
    def _vmware_get_hosts(self, host_metrics):
        """
        Get Host (ESXi) information
        """
        logging.info("Starting host metrics collection")

        results, host_labels = yield parallelize(self.host_system_inventory, self.host_labels)

        for host_id, host in results.items():
            try:
                labels = host_labels[host_id]
            except KeyError as e:
                logging.info(
                    "Key error, unable to register host {error}, host labels are {host_labels}".format(
                        error=e, host_labels=host_labels
                    )
                )
                continue

            # Power state
            power_state = 1 if host['runtime.powerState'] == 'poweredOn' else 0
            host_metrics['vmware_host_power_state'].add_metric(labels, power_state)

            # Host connection state (connected, disconnected, notResponding)
            connection_state = host.get('runtime.connectionState', 'unknown')
            host_metrics['vmware_host_connection_state'].add_metric(
                labels + [connection_state],
                1
            )

            if not power_state:
                continue

            if host.get('runtime.bootTime'):

                # Host uptime
                host_metrics['vmware_host_boot_timestamp_seconds'].add_metric(
                    labels,
                    self._to_epoch(host['runtime.bootTime'])
                )

            # Host in maintenance mode?
            if 'runtime.inMaintenanceMode' in host:
                host_metrics['vmware_host_maintenance_mode'].add_metric(
                    labels,
                    host['runtime.inMaintenanceMode'] * 1,
                )

            # CPU Usage (in Mhz)
            if 'summary.quickStats.overallCpuUsage' in host:
                host_metrics['vmware_host_cpu_usage'].add_metric(
                    labels,
                    host['summary.quickStats.overallCpuUsage'],
                )

            cpu_core_num = host.get('summary.hardware.numCpuCores')
            if cpu_core_num:
                host_metrics['vmware_host_num_cpu'].add_metric(labels, cpu_core_num)

            cpu_mhz = host.get('summary.hardware.cpuMhz')
            if cpu_core_num and cpu_mhz:
                cpu_total = cpu_core_num * cpu_mhz
                host_metrics['vmware_host_cpu_max'].add_metric(labels, cpu_total)

            # Memory Usage (in MB)
            if 'summary.quickStats.overallMemoryUsage' in host:
                host_metrics['vmware_host_memory_usage'].add_metric(
                    labels,
                    host['summary.quickStats.overallMemoryUsage']
                )

            if 'summary.hardware.memorySize' in host:
                host_metrics['vmware_host_memory_max'].add_metric(
                    labels,
                    float(host['summary.hardware.memorySize']) / 1024 / 1024
                )

        logging.info("Finished host metrics collection")
        return results


class ListCollector(object):

    def __init__(self, metrics):
        self.metrics = list(metrics)

    def collect(self):
        return self.metrics


class VMWareMetricsResource(Resource):

    isLeaf = True

    def __init__(self, args):
        """
        Init Metric Resource
        """
        Resource.__init__(self)
        self.configure(args)

    def configure(self, args):
        if args.config_file:
            try:
                self.config = YamlConfig(args.config_file)
                if 'default' not in self.config.keys():
                    logging.error("Error, you must have a default section in config file (for now)")
                    exit(1)
                return
            except Exception as exception:
                raise SystemExit("Error while reading configuration file: {0}".format(exception.message))

        self.config = {
            'default': {
                'vsphere_host': os.environ.get('VSPHERE_HOST'),
                'vsphere_user': os.environ.get('VSPHERE_USER'),
                'vsphere_password': os.environ.get('VSPHERE_PASSWORD'),
                'ignore_ssl': get_bool_env('VSPHERE_IGNORE_SSL', False),
                'collect_only': {
                    'vms': get_bool_env('VSPHERE_COLLECT_VMS', True),
                    'vmguests': get_bool_env('VSPHERE_COLLECT_VMGUESTS', True),
                    'datastores': get_bool_env('VSPHERE_COLLECT_DATASTORES', True),
                    'hosts': get_bool_env('VSPHERE_COLLECT_HOSTS', True),
                    'snapshots': get_bool_env('VSPHERE_COLLECT_SNAPSHOTS', True),
                }
            }
        }

        for key in os.environ.keys():
            if key == 'VSPHERE_USER':
                continue
            if not key.startswith('VSPHERE_') or not key.endswith('_USER'):
                continue

            section = key.split('_', 1)[1].rsplit('_', 1)[0]

            self.config[section.lower()] = {
                'vsphere_host': os.environ.get('VSPHERE_{}_HOST'.format(section)),
                'vsphere_user': os.environ.get('VSPHERE_{}_USER'.format(section)),
                'vsphere_password': os.environ.get('VSPHERE_{}_PASSWORD'.format(section)),
                'ignore_ssl': get_bool_env('VSPHERE_{}_IGNORE_SSL'.format(section), False),
                'collect_only': {
                    'vms': get_bool_env('VSPHERE_{}_COLLECT_VMS'.format(section), True),
                    'vmguests': get_bool_env('VSPHERE_{}_COLLECT_VMGUESTS'.format(section), True),
                    'datastores': get_bool_env('VSPHERE_{}_COLLECT_DATASTORES'.format(section), True),
                    'hosts': get_bool_env('VSPHERE_{}_COLLECT_HOSTS'.format(section), True),
                    'snapshots': get_bool_env('VSPHERE_{}_COLLECT_SNAPSHOTS'.format(section), True),
                }
            }

    def render_GET(self, request):
        """ handles get requests for metrics, health, and everything else """
        self._async_render_GET(request)
        return NOT_DONE_YET

    @defer.inlineCallbacks
    def _async_render_GET(self, request):
        try:
            yield self.generate_latest_metrics(request)
        except Exception:
            logging.error(traceback.format_exc())
            request.setResponseCode(500)
            request.write(b'# Collection failed')
            request.finish()

        # We used to call request.processingFailed to send a traceback to browser
        # This can make sense in debug mode for a HTML site - but we don't want
        # prometheus trying to parse a python traceback

    @defer.inlineCallbacks
    def generate_latest_metrics(self, request):
        """ gets the latest metrics """
        section = request.args.get(b'section', [b'default'])[0].decode('utf-8')
        if section not in self.config.keys():
            logging.info("{} is not a valid section, using default".format(section))
            section = 'default'

        if self.config[section].get('vsphere_host') and self.config[section].get('vsphere_host') != "None":
            vsphere_host = self.config[section].get('vsphere_host')
        elif request.args.get(b'target', [None])[0]:
            vsphere_host = request.args.get(b'target', [None])[0].decode('utf-8')
        elif request.args.get(b'vsphere_host', [None])[0]:
            vsphere_host = request.args.get(b'vsphere_host')[0].decode('utf-8')
        else:
            request.setResponseCode(500)
            logging.info("No vsphere_host or target defined")
            request.write(b'No vsphere_host or target defined!\n')
            request.finish()
            return

        collector = VmwareCollector(
            vsphere_host,
            self.config[section]['vsphere_user'],
            self.config[section]['vsphere_password'],
            self.config[section]['collect_only'],
            self.config[section]['ignore_ssl'],
        )
        metrics = yield collector.collect()

        registry = CollectorRegistry()
        registry.register(ListCollector(metrics))
        output = generate_latest(registry)

        request.setHeader("Content-Type", "text/plain; charset=UTF-8")
        request.setResponseCode(200)
        request.write(output)
        request.finish()


class HealthzResource(Resource):

    isLeaf = True

    def render_GET(self, request):
        request.setHeader("Content-Type", "text/plain; charset=UTF-8")
        request.setResponseCode(200)
        logging.info("Service is UP")
        return 'Server is UP'.encode()


class IndexResource(Resource):
    isLeaf = False

    def getChild(self, name, request):
        if name == b'':
            return self
        return Resource.getChild(self, name, request)

    def render_GET(self, request):
        output = """<html>
            <head><title>VMware Exporter</title></head>
            <body>
            <h1>VMware Exporter</h1>
            <p><a href="/metrics">Metrics</a></p>
            </body>
            </html>"""
        request.setHeader("Content-Type", "text/html; charset=UTF-8")
        request.setResponseCode(200)
        return output.encode()


def registerEndpoints(args):
    root = Resource()
    root.putChild(b'', IndexResource())
    root.putChild(b'metrics', VMWareMetricsResource(args))
    root.putChild(b'healthz', HealthzResource())
    return root


def main(argv=None):
    """ start up twisted reactor """
    parser = argparse.ArgumentParser(description='VMWare metrics exporter for Prometheus')
    parser.add_argument('-c', '--config', dest='config_file',
                        default=None, help="configuration file")
    parser.add_argument('-p', '--port', dest='port', type=int,
                        default=9272, help="HTTP port to expose metrics")
    parser.add_argument('-l', '--loglevel', dest='loglevel',
                        default="INFO", help="Set application loglevel INFO, DEBUG")

    args = parser.parse_args(argv or sys.argv[1:])

    numeric_level = getattr(logging, args.loglevel.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError("Invalid log level: {level}".format(level=args.loglevel))
    logging.basicConfig(level=numeric_level, format='%(asctime)s %(levelname)s:%(message)s')

    reactor.suggestThreadPoolSize(25)

    factory = Site(registerEndpoints(args))
    logging.info("Starting web server on port {port}".format(port=args.port))
    endpoint = endpoints.TCP4ServerEndpoint(reactor, args.port)
    endpoint.listen(factory)
    reactor.run()


if __name__ == '__main__':
    main()
