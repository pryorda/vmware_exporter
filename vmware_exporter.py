#!/usr/bin/env python

from __future__ import print_function

# Generic imports
import atexit
import argparse
import sys
import time
import ssl
import pytz

from datetime import datetime
from yamlconfig import YamlConfig

# VMWare specific imports
from pyVmomi import vim, vmodl
from pyVim import connect

# Prometheus specific imports
from prometheus_client import start_http_server, Counter, Gauge, Summary
from prometheus_client.core import GaugeMetricFamily, REGISTRY

defaults = {
            'vcenter_ip': 'localhost',
            'vcenter_user': 'administrator@vsphere.local',
            'vcenter_password': 'password',
            'ignore_ssl': True
            }

class VMWareVCenterCollector(object):

    config = YamlConfig('config.yml', defaults)

    def collect(self):

        vm_metrics = [
                    GaugeMetricFamily(
                        'vmware_vm_power_state',
                        'VMWare VM Power state (On / Off)',
                        labels=['vm_name']),
                    GaugeMetricFamily(
                        'vmware_vm_boot_timestamp_seconds',
                        'VMWare VM boot time in seconds',
                        labels=['vm_name']),
        ]

        snap_metrics = [
                    GaugeMetricFamily(
                        'vmware_vm_snapshots',
                        'VMWare current number of existing snapshots',
                        labels=['vm_name']),
                    GaugeMetricFamily(
                        'vmware_vm_napshot_timestamp_seconds',
                        'VMWare Snapshot creation time in seconds',
                        labels=['vm_name', 'vm_snapshot_name']),
                ]

        ds_metrics = [
                    GaugeMetricFamily(
                        'vmware_datastore_capacity_size',
                        'VMWare Datasore capacity in bytes',
                        labels=['ds_name']),
                    GaugeMetricFamily(
                        'vmware_datastore_freespace_size',
                        'VMWare Datastore freespace in bytes',
                        labels=['ds_name']),
                    GaugeMetricFamily(
                        'vmware_datastore_uncommited_size',
                        'VMWare Datastore uncommitted in bytes',
                        labels=['ds_name']),
                    GaugeMetricFamily(
                        'vmware_datastore_provisoned_size',
                        'VMWare Datastore provisoned in bytes',
                        labels=['ds_name']),
                    GaugeMetricFamily(
                        'vmware_datastore_hosts',
                        'VMWare Hosts number using this datastore',
                        labels=['ds_name']),
                    GaugeMetricFamily(
                        'vmware_datastore_vms',
                        'VMWare Virtual Machines number using this datastore',
                        labels=['ds_name'])
                ]

        host_metrics = [
                    GaugeMetricFamily(
                        'vmware_host_power_state',
                        'VMWare Host Power state (On / Off)',
                        labels=['host_name']),
                    GaugeMetricFamily(
                        'vmware_host_boot_timestamp_seconds',
                        'VMWare Host boot time in seconds',
                        labels=['host_name']),
                ]

        print("[{0}] Start collecting vcenter metrics".format(datetime.utcnow().replace(tzinfo=pytz.utc)))

        # Get VMWare VM Informations
        content = self._vmware_get_content()

        # Fill Snapshots (count and age)
        vm_counts, vm_ages = self._vmware_get_snapshots(content)
        for v in vm_counts:
            snap_metrics[0].add_metric([v['vm_name']], v['snapshot_count'])
        for vm_age in vm_ages:
            for v in vm_age:
                snap_metrics[1].add_metric([v['vm_name'], v['vm_snapshot_name']],
                                        v['vm_snapshot_timestamp_seconds'])

        # Fill Datastore
        self._vmware_get_datastores(content, ds_metrics)

        # Fill VM Informations
        self._vmware_get_vms(content, vm_metrics)

        # Fill Hosts Informations
        self._vmware_get_hosts(content, host_metrics)

        print("[{0}] Stop Collecting".format(datetime.utcnow().replace(tzinfo=pytz.utc)))

        # Fill all metrics
        for m in vm_metrics + snap_metrics + ds_metrics + host_metrics:
            yield m


    def _to_unix_timestamp(self, my_date):
        return ((my_date - datetime(1970,1,1,tzinfo=pytz.utc)).total_seconds())

    def _vmware_get_obj(self, content, vimtype, name=None):
        """
         Get the vsphere object associated with a given text name
        """
        obj = None
        container = content.viewManager.CreateContainerView(
            content.rootFolder, vimtype, True)
        if name:
            for c in container.view:
                if c.name == name:
                    obj = c
                    return [obj]
        else:
            return container.view

    def _vmware_get_content(self):
        """
        Connect to Vcenter and get all VM Content Information
        """

        si = None

        context = None
        if self.config['main']['ignore_ssl'] and \
                hasattr(ssl, "_create_unverified_context"):
            context = ssl._create_unverified_context()

        try:
            si = connect.Connect(self.config['main']['vcenter_ip'], 443,
                                 self.config['main']['vcenter_user'],
                                 self.config['main']['vcenter_password'],
                                 sslContext=context)

            atexit.register(connect.Disconnect, si)

            content = si.RetrieveContent()
            return content

        except vmodl.MethodFault as error:
            print("Caught vmodl fault : " + error.msg)
            return -1


    def _vmware_list_snapshots_recursively(self, snapshots):
        """
        Get snapshots from a VM list, recursively
        """
        snapshot_data = []
        for snapshot in snapshots:
            snap_timestamp = self._to_unix_timestamp(snapshot.createTime)
            snap_info = {
                            'vm_snapshot_name': snapshot.name,
                            'vm_snapshot_timestamp_seconds': snap_timestamp
                        }
            snapshot_data.append(snap_info)
            snapshot_data = snapshot_data + self._vmware_list_snapshots_recursively(
                                            snapshot.childSnapshotList)
        return snapshot_data


    def _vmware_get_snapshots(self, content):
        """
        Get snapshots from all VM
        """
        snapshots_count_table = []
        snapshots_age_table = []
        for vm in self._vmware_get_obj(content, [vim.VirtualMachine]):

            if not vm or vm.snapshot is None:
                continue

            else:
                snapshot_paths = self._vmware_list_snapshots_recursively(
                                    vm.snapshot.rootSnapshotList)
                for sn in snapshot_paths:
                    sn['vm_name'] = vm.name
                # Add Snapshot count per VM
                snapshot_count = len(snapshot_paths)
                snapshot_count_info = {
                    'vm_name': vm.name,
                    'snapshot_count': snapshot_count
                }
                snapshots_count_table.append(snapshot_count_info)
            snapshots_age_table.append(snapshot_paths)
        return snapshots_count_table, snapshots_age_table


    def _vmware_get_datastores(self, content, ds_metrics):
        """
        Get Datastore information
        """
        for ds in self._vmware_get_obj(content, [vim.Datastore]):
            summary = ds.summary
            ds_capacity = summary.capacity
            ds_freespace = summary.freeSpace
            ds_uncommitted = summary.uncommitted if summary.uncommitted else 0
            ds_provisioned = ds_capacity - ds_freespace + ds_uncommitted

            ds_metrics[0].add_metric([summary.name], ds_capacity)
            ds_metrics[1].add_metric([summary.name], ds_freespace)
            ds_metrics[2].add_metric([summary.name], ds_uncommitted)
            ds_metrics[3].add_metric([summary.name], ds_provisioned)
            ds_metrics[4].add_metric([summary.name], len(ds.host))
            ds_metrics[5].add_metric([summary.name], len(ds.vm))


    def _vmware_get_vms(self, content, vm_metrics):
        """
        Get VM information
        """
        for vm in self._vmware_get_obj(content, [vim.VirtualMachine]):
            summary = vm.summary
            power_state = 1 if summary.runtime.powerState == 'poweredOn' else 0
            vm_metrics[0].add_metric([vm.name], power_state)
            if summary.runtime.bootTime:
                vm_metrics[1].add_metric([vm.name],
                            self._to_unix_timestamp(summary.runtime.bootTime))


    def _vmware_get_hosts(self, content, host_metrics):
        """
        Get Host (ESXi) information
        """
        for host in self._vmware_get_obj(content, [vim.HostSystem]):
            summary = host.summary
            power_state = 1 if summary.runtime.powerState == 'poweredOn' else 0
            host_metrics[0].add_metric([host.name], power_state)
            if summary.runtime.bootTime:
                host_metrics[1].add_metric([host.name],
                            self._to_unix_timestamp(summary.runtime.bootTime))
if __name__ == '__main__':
    REGISTRY.register(VMWareVCenterCollector())
    # Start up the server to expose the metrics.
    start_http_server(8000)
    # Generate some requests.
    while True:
        time.sleep(1)
