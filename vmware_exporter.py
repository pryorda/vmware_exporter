#!/usr/bin/env python

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

class VMWareSnapshotsCollector(object):

    config = YamlConfig('config.yml', defaults)

    def collect(self):
        metric= [
                    GaugeMetricFamily(
                        'vmware_snapshots',
                        'VMWare current number of existing snapshots',
                        labels=['vm_name']),
                    GaugeMetricFamily(
                        'vmware_snapshot_timestamp_seconds',
                        'VMWare Snapshot creation time in seconds',
                        labels=['vm_name', 'vm_snapshot_name'])
                ]


        print("Collecting snapshots")
        print("Begin: %s" % datetime.utcnow().replace(tzinfo=pytz.utc))

        # Get VMWare VM Informations
        content = self._vmware_get_content()

        # Fill Snapshots (count and age)
        vm_counts, vm_ages = self._vmware_get_snapshots(content)
        for v in vm_counts:
            metric[0].add_metric([v['vm_name']], v['snapshot_count'])
        for vm_age in vm_ages:
            for v in vm_age:
                metric[1].add_metric([v['vm_name'], v['vm_snapshot_name']],
                                        v['vm_snapshot_timestamp_seconds'])

        print("End: %s" % datetime.utcnow().replace(tzinfo=pytz.utc))

        # Fill all metrics
        for m in metric:
            yield m


    def _vmware_get_obj(self, content, vimtype, name):
        """
         Get the vsphere object associated with a given text name
        """
        obj = None
        container = content.viewManager.CreateContainerView(
            content.rootFolder, vimtype, True)
        for c in container.view:
            if c.name == name:
                obj = c
                break
        return obj


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

    def _vmware_list_vms(self, content):
        """
        Get the Virtual machine lists from VMWare Content
        """
        container = content.rootFolder  # starting point to look into
        viewType = [vim.VirtualMachine]  # object types to look for
        recursive = True  # whether we should look into it recursively
        containerView = content.viewManager.CreateContainerView(
            container, viewType, recursive)

        children = containerView.view
        return children


    def _vmware_list_snapshots_recursively(self, snapshots):
        """
        Get snapshots from a VM list, recursively
        """
        snapshot_data = []
        for snapshot in snapshots:
            snap_timestamp = (snapshot.createTime - datetime(1970,1,1,tzinfo=pytz.utc)).total_seconds()
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
        for child in self._vmware_list_vms(content):
            summary = child.summary

            vm = self._vmware_get_obj(content, [vim.VirtualMachine], summary.config.name)

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



if __name__ == '__main__':
    REGISTRY.register(VMWareSnapshotsCollector())
    # Start up the server to expose the metrics.
    start_http_server(8000)
    # Generate some requests.
    while True:
        time.sleep(1)
