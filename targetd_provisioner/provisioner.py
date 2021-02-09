# Copyright (C) 2021 Johan Fleury <jfleury@arcaik.net>
#
# This file is part of targetd-client.
#
# targetd-client is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# targetd-client is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with targetd-client.  If not, see <https://www.gnu.org/licenses/>.

import kopf
import kubernetes

from targetd_client import TargetdClient, TargetdException

from kubernetes.utils import parse_quantity

from .meta import CONTROLLER_NAME


REQUIRED_PARAMETERS = (
    "pool",
    "portals",
    "target",
    "initiatorName",
)


class Provisioner(object):
    def __init__(
        self,
        name: str,
        api_url: str,
        api_username: str,
        api_password: str,
        api_insecure_skip_verify: bool,
    ):
        self.name = name
        self.targetd = TargetdClient(
            api_url, api_username, api_password, api_insecure_skip_verify
        )
        self.storage_classes = {}

        self.register_handlers()

    def register_handlers(self):
        kopf.on.startup()(self.configure)

        kopf.on.event(
            "storage.k8s.io",
            "v1",
            "storageclasses",
            when=self.filter_storage_class,
        )(self.cache_storage_class)

        kopf.on.resume(
            "",
            "v1",
            "persistentvolumeclaims",
            when=self.filter_persistent_volume_claims_creation,
        )(self.create)

        kopf.on.create(
            "",
            "v1",
            "persistentvolumeclaims",
            when=self.filter_persistent_volume_claims_creation,
        )(self.create)

        kopf.on.delete(
            "",
            "v1",
            "persistentvolumeclaims",
            when=self.filter_persistent_volume_claims_deletion,
        )(self.delete)

        kopf.on.update(
            "",
            "v1",
            "persistentvolumeclaims",
            field="spec.resources.requests.storage",
            when=self.filter_persistent_volume_claims,
        )(self.resize)

    def configure(self, settings: kopf.OperatorSettings, **_):
        settings.persistence.finalizer = f"{CONTROLLER_NAME}/finalizer"
        settings.persistence.progress_storage = kopf.StatusProgressStorage(
            field="status.targetd-provisioner"
        )
        settings.scanning.disabled = True

    def cache_storage_class(self, logger, event, name, body, **_):
        if event["type"] == "DELETED" and name in self.storage_classes:
            del self.storage_classes[name]
            return

        missing_parameters = set()
        for param in REQUIRED_PARAMETERS:
            if param not in body["parameters"]:
                missing_parameters.add(param)

        if missing_parameters:
            error = f"missing parameters: {', '.join(missing_parameters)}"
            logger.warning("Not watching PVCs for this storage class: {error}")
            raise kopf.PermanentError(error)

        self.storage_classes[name] = body

    def create(self, logger, name, namespace, uid, meta, spec, **_):
        storage_class = self.storage_classes[spec["storageClassName"]]

        pool = storage_class["parameters"]["pool"]
        portals = storage_class["parameters"]["portals"].split(",")
        target = storage_class["parameters"]["target"]
        initiator_name = storage_class["parameters"]["initiatorName"]
        fs_type = storage_class["parameters"].get("fsType", "ext4")

        pv_name = f"pvc-{uid}"
        pv_size = int(parse_quantity(spec["resources"]["requests"]["storage"]))
        pv_access_mode = spec["accessModes"]

        if "ReadWriteMany" in pv_access_mode:
            raise kopf.PermanentError(f"access mode not supported: {pv_access_mode}")

        try:
            self.targetd.vol_create(pool, pv_name, pv_size)
        except TargetdException as e:
            if e.code != TargetdException.NAME_CONFLICT:
                raise kopf.TemporaryError(f"unable to create volume: {e}")

        lun = self.targetd.export_create(pool, pv_name, initiator_name)

        persistent_volume = kubernetes.client.V1PersistentVolume(
            metadata=kubernetes.client.V1ObjectMeta(
                name=pv_name,
                annotations={
                    f"{CONTROLLER_NAME}/pool": pool,
                    f"{CONTROLLER_NAME}/initiatorName": initiator_name,
                },
            ),
            spec=kubernetes.client.V1PersistentVolumeSpec(
                storage_class_name=spec["storageClassName"],
                persistent_volume_reclaim_policy=storage_class["reclaimPolicy"],
                access_modes=pv_access_mode,
                capacity={"storage": spec["resources"]["requests"]["storage"]},
                volume_mode=spec["volumeMode"],
                iscsi=kubernetes.client.V1ISCSIPersistentVolumeSource(
                    target_portal=portals[0],
                    portals=portals,
                    iqn=target,
                    lun=lun,
                    initiator_name=initiator_name,
                    fs_type=fs_type,
                ),
            ),
        )

        api = kubernetes.client.CoreV1Api()
        api.create_persistent_volume(persistent_volume, field_manager=CONTROLLER_NAME)

    def delete(self, logger, spec, **_):
        pv_name = spec["volumeName"]

        api = kubernetes.client.CoreV1Api()
        persistent_volume = api.read_persistent_volume(pv_name)

        if persistent_volume.spec.persistent_volume_reclaim_policy == "Retain":
            logger.Info(
                f"Skipping deletion of persistent volume {pv_name}:"
                "reclaim policy is set to Retain"
            )
            return

        pool = persistent_volume.metadata.annotations[f"{CONTROLLER_NAME}/pool"]
        initiator_name = persistent_volume.metadata.annotations[
            f"{CONTROLLER_NAME}/initiatorName"
        ]

        try:
            self.targetd.export_destroy(pool, pv_name, initiator_name)
        except TargetdException as e:
            if e.code != TargetdException.NOT_FOUND_VOLUME_EXPORT:
                raise kopf.TemporaryError(f"Unable to delete ISCSI export: {e}")

        try:
            self.targetd.vol_destroy(pool, pv_name)
        except TargetdException as e:
            if e.code != TargetdException.NOT_FOUND_VOLUME:
                raise kopf.TemporaryError(f"Unable to delete peristent volume: {e}")

        api.delete_persistent_volume(pv_name)

    def resize(self, old, new, **_):
        raise kopf.TemporaryError("Not implemented yet")

    def filter_storage_class(self, body, **_):
        return body["provisioner"] == self.name

    def filter_persistent_volume_claims(self, annotations, **_):
        return (
            annotations.get("volume.beta.kubernetes.io/storage-provisioner", None)
            == self.name
        )

    def filter_persistent_volume_claims_creation(self, annotations, status, **_):
        if status.get("phase", None) != "Pending":
            return False

        return self.filter_persistent_volume_claims(annotations)

    def filter_persistent_volume_claims_deletion(self, annotations, status, **_):
        if status.get("phase", None) != "Bound":
            return False

        return self.filter_persistent_volume_claims(annotations)
