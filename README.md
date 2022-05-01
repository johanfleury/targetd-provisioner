# targetd-provisioner

targetd-provisioner is a storage provisoner for Kubernetes that uses targetd as
a backend.

## Usage

### ISCSI

The iscsi provisioner excepts the following StorageClass parameters:

| Parameter | Description |
|-----------|-------------|
| `targetd-provisioner/pool` | The targetd pool in which to create volumes. **Required**. |
| `targetd-provisioner/target` | Target’s IQN (the value of `target_name` in `targetd.yaml`). **Required**. |
| `targetd-provisioner/portals` | A comma separated list of portals IPs or hostnames. **Required**. |
| `targetd-provisioner/initiators` | A comma separated list of initiator’s IQN. **Required**. |
| `fsType` | The type of filesystem use to format the volume. Must be supported by Kubernetes. **Optional** (default: ext4). |


See [`example/iscsi.yaml`](example/iscsi.yaml) for an example on how to create
a StorageClass and PersistentVolumeClaim for use with the ISCSI provisioner.

## Contributing

This library is [Free Software](LICENSE) and every contributions are welcome.

Please note that this project is released with a [Contributor Code of
Conduct](CODE_OF_CONDUCT.md). By participating in this project you agree to
abide by its terms.
