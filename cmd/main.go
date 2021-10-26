package main

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
	"gitlab.com/Arcaik/external-provisioner/pkg/controller"
	"gitlab.com/Arcaik/external-provisioner/pkg/version"

	"gitlab.com/Arcaik/targetd-provisioner/internal/provisioner"
)

var (
	targetdURL string
)

func main() {
	cmd := &cobra.Command{
		Use:     "targetd-provisioner",
		Short:   "A dynamic provisioner for Kubernetes using targetd",
		Version: version.Version,
		PersistentPreRunE: func(cmd *cobra.Command, _ []string) error {
			if targetdURL == "" {
				if v := os.Getenv("TARGETD_PROVISIONER_URL"); v != "" {
					cmd.PersistentFlags().Set("targetd-url", v)
				}
			}

			if targetdURL == "" {
				return fmt.Errorf("\"targetd-url\" must not be empty")
			}

			return nil
		},
		Run: func(_ *cobra.Command, _ []string) {
			p := provisioner.NewISCSIProvisionner(targetdURL)
			pc, err := controller.NewProvisioningController(p)
			if err != nil {
				fmt.Printf("Unable to create controller: %s\n", err)
				os.Exit(1)
			}

			if err := pc.Start(); err != nil {
				fmt.Printf("Problem running manager: %s\n", err)
				os.Exit(1)
			}
		},
	}

	controller.InitFlags(cmd)

	cmd.PersistentFlags().StringVar(&targetdURL, "targetd-url", "", ""+
		"URL of the targetd API (it can also be set throught the TARGETD_PROVISIONER_URL environement variable).")
	cmd.MarkPersistentFlagRequired("targetd-url")

	if err := cmd.Execute(); err != nil {
		os.Exit(1)
	}
}
