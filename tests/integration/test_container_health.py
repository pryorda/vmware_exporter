from pytest_docker_tools import container, build
import requests


vmware_exporter_image = build(path='.')

vmware_exporter = container(
    image='{vmware_exporter_image.id}',
    ports={
        '9272/tcp': None,
    },
)


def test_container_starts(vmware_exporter):
    container_addr = vmware_exporter.get_addr('9272/tcp')
    assert requests.get('http://{}:{}/healthz'.format(*container_addr)).status_code == 200


def test_container_404(vmware_exporter):
    container_addr = vmware_exporter.get_addr('9272/tcp')
    assert requests.get('http://{}:{}/meetrics'.format(*container_addr)).status_code == 404
