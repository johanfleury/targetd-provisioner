package provisioner

import (
	"fmt"
	"strings"

	"gitlab.com/Arcaik/external-provisioner/pkg/controller"
	"gitlab.com/Arcaik/targetd-client-go/pkg/targetd"
	v1 "k8s.io/api/core/v1"
	storagev1 "k8s.io/api/storage/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// AccessModesContains returns whether the requested mode is contained by modes
func AccessModesContains(modes []v1.PersistentVolumeAccessMode, mode v1.PersistentVolumeAccessMode) bool {
	for _, m := range modes {
		if m == mode {
			return true
		}
	}

	return false
}

// AccessModesContainedInAll returns whether all of the requested modes are contained by modes
func AccessModesContainedInAll(modes []v1.PersistentVolumeAccessMode, requestedModes []v1.PersistentVolumeAccessMode) bool {
	for _, mode := range requestedModes {
		if !AccessModesContains(modes, mode) {
			return false
		}
	}

	return true
}

type ISCSIProvisioner struct {
	targetd *targetd.Client
}

func NewISCSIProvisionner(url string) *ISCSIProvisioner {
	return &ISCSIProvisioner{
		targetd: targetd.New(url),
	}
}

func (p *ISCSIProvisioner) Name() string {
	return "targetd-provisioner-iscsi"
}

func (p *ISCSIProvisioner) Provision(options controller.ProvisionOptions) (*v1.PersistentVolume, error) {
	if !AccessModesContainedInAll(p.getAllowedAccessModes(), options.PersistentVolumeClaim.Spec.AccessModes) {
		return nil, fmt.Errorf("invalid AccessModes %v: only %v are supported", options.PersistentVolumeClaim.Spec.AccessModes, p.getAllowedAccessModes())
	}

	pool, target, portals, initiators, fsType, err := p.parseStorageClassParameters(options.StorageClass)
	if err != nil {
		return nil, err
	}

	size := options.PersistentVolumeClaim.Spec.Resources.Requests.Storage()

	if err := p.targetd.VolCreate(pool, options.VolumeName, size.Value()); err != nil {
		// NOTE: this is probably safe because k8s ensure PV names are unique.
		if e := targetd.UnwrapError(err); e == nil || e.Code() != targetd.NameConflictError {
			return nil, fmt.Errorf("unable to create volume: %s", formatTargetdError(err))
		}
	}

	lun, err := p.targetd.GetFirstAvailableLun()
	if err != nil {
		return nil, fmt.Errorf("unable to find an available LUN: %s", formatTargetdError(err))
	}

	for _, initiator := range initiators {
		if err := p.targetd.ExportCreate(pool, options.VolumeName, initiator, lun); err != nil {
			return nil, fmt.Errorf("unable to create export: %s", formatTargetdError(err))
		}
	}

	pv := &v1.PersistentVolume{
		ObjectMeta: metav1.ObjectMeta{
			Name: options.VolumeName,
			Annotations: map[string]string{
				"targetd-provisioner/pool":       pool,
				"targetd-provisioner/initiators": strings.Join(initiators, ","),
			},
		},
		Spec: v1.PersistentVolumeSpec{
			// XXX: We should verify that those AccessModes make sense in our context
			AccessModes:                   options.PersistentVolumeClaim.Spec.AccessModes,
			PersistentVolumeReclaimPolicy: *options.StorageClass.ReclaimPolicy,
			MountOptions:                  options.StorageClass.MountOptions,
			Capacity: v1.ResourceList{
				v1.ResourceName(v1.ResourceStorage): *size,
			},
			PersistentVolumeSource: v1.PersistentVolumeSource{
				// XXX: Add support for authentication
				ISCSI: &v1.ISCSIPersistentVolumeSource{
					TargetPortal: portals[0],
					Portals:      portals,
					IQN:          target,
					Lun:          lun,
					FSType:       fsType,
				},
			},
		},
	}

	return pv, nil
}

func (p *ISCSIProvisioner) getAllowedAccessModes() []v1.PersistentVolumeAccessMode {
	return []v1.PersistentVolumeAccessMode{
		v1.ReadWriteOnce,
		v1.ReadOnlyMany,
	}
}

func (p *ISCSIProvisioner) parseStorageClassParameters(class *storagev1.StorageClass) (pool string, target string, portals []string, initiators []string, fsType string, err error) {
	// Transient variable to store values that needs more parsing
	var v string
	var ok bool

	pool, ok = class.Parameters["targetd-provisioner/pool"]
	if !ok {
		err = fmt.Errorf("StorageClass parameter targetd-provisioner/pool is required")
		return
	}

	target, ok = class.Parameters["targetd-provisioner/target"]
	if !ok {
		err = fmt.Errorf("StorageClass parameter targetd-provisioner/target is required")
		return
	}

	if v, ok = class.Parameters["targetd-provisioner/portals"]; ok {
		portals = strings.Split(v, ",")
	} else {
		err = fmt.Errorf("StorageClass parameter targetd-provisioner/portals is required")
		return
	}

	if v, ok = class.Parameters["targetd-provisioner/initiators"]; ok {
		initiators = strings.Split(v, ",")
	} else {
		err = fmt.Errorf("StorageClass parameter targetd-provisioner/initiators is required")
	}

	fsType, ok = class.Parameters["fsType"]
	if !ok {
		fsType = "ext4"
	}

	return
}

func (p *ISCSIProvisioner) Delete(pv *v1.PersistentVolume) error {
	pool, ok := pv.Annotations["targetd-provisioner/pool"]
	if !ok {
		return fmt.Errorf("annotation `targetd-provisioner/pool` is missing on PersistentVolume")
	}

	initiators, ok := pv.Annotations["targetd-provisioner/initiators"]
	if !ok {
		return fmt.Errorf("annotation `targetd-provisioner/initiators` is missing on PersistentVolume")
	}

	for _, initiator := range strings.Split(initiators, ",") {
		if err := p.targetd.ExportDestroy(pool, pv.ObjectMeta.Name, initiator); err != nil {
			if e := targetd.UnwrapError(err); e != nil && e.Code() == targetd.VolumeExportNotFoundError {
				// Export not found
				continue
			}

			return fmt.Errorf("Unable to remove export: %s", formatTargetdError(err))
		}
	}

	if err := p.targetd.VolDestroy(pool, pv.ObjectMeta.Name); err != nil {
		if e := targetd.UnwrapError(err); e != nil && e.Code() == targetd.VolumeNotFoundError {
			// Volume not found
			return nil
		}

		return fmt.Errorf("Unable to remove volume: %s", formatTargetdError(err))
	}

	return nil
}

func (p *ISCSIProvisioner) Resize(pv *v1.PersistentVolume, size int64) error {
	pool, ok := pv.Annotations["targetd-provisioner/pool"]
	if !ok {
		return fmt.Errorf("annotation `targetd-provisioner/pool` is missing on PersistentVolume")
	}

	if err := p.targetd.VolResize(pool, pv.ObjectMeta.Name, size); err != nil {
		// Volume is already of the same size or bigger
		// Warning code -32602 is a generic code for “invalid parameter”
		if e := targetd.UnwrapError(err); e != nil && e.Code() == -32602 {
			return nil
		}

		return fmt.Errorf("Unable to resize volume: %s", formatTargetdError(err))
	}

	return nil
}

func formatTargetdError(err error) string {
	if e := targetd.UnwrapError(err); err != nil {
		return e.String()
	}

	return err.Error()
}
