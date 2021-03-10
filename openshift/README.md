### Installing vmware_exporter in OpenShift

Create the secret as described in the kubernetes documentation

TODO: Use existing secret
```
read -s VSPHERE_PASSWORD
oc create secret generic -n openshift-vsphere-infra vmware-exporter-password --from-literal=VSPHERE_PASSWORD=$VSPHERE_PASSWORD
```

Modify the `configmap.yaml` for your configuration and apply.

```
oc apply -f configmap.yaml
```

Apply the role, rolebinding, service, deployment and ServiceMonitor

```
oc apply -f rolebinding.yaml
oc apply -f service.yaml
oc apply -f deployment.yaml
oc apply -f servicemonitor.yaml
```



