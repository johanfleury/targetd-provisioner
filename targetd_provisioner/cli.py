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

import click
import kopf

from .provisioner import Provisioner


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option(
    "--provisioner-name",
    envvar="TARGETD_PROVISIONER_NAME",
    default="targetd",
    required=True,
)
@click.option("--api-url", envvar="TARGETD_PROVISIONER_API_URL", required=True)
@click.option(
    "--api-username", envvar="TARGETD_PROVISIONER_API_USERNAME", required=True
)
@click.option(
    "--api-password", envvar="TARGETD_PROVISIONER_API_PASSWORD", required=True
)
@click.option(
    "--api-insecure-skip-verify",
    envvar="TARGETD_PROVISIONER_API_INSECURE_SKIP_VERIFY",
    is_flag=True,
)
@click.option(
    "--log-level",
    envvar="TARGETD_PROVISIONER_LOG_LEVEL",
    type=click.Choice(["debug", "info", "warning"], case_sensitive=False),
    default="info",
)
@click.option(
    "--log-format",
    envvar="TARGETD_PROVISIONER_LOG_FORMAT",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
)
@click.option(
    "--liveness-endpoint",
    envvar="TARGETD_PROVISIONER_LIVENESS_ENDPOINT",
    default="http://0.0.0.0:8080/live",
)
def main(
    provisioner_name: str,
    api_url: str,
    api_username: str,
    api_password: str,
    api_insecure_skip_verify: bool,
    log_format: str,
    log_level: str,
    liveness_endpoint: str,
):
    Provisioner(
        provisioner_name, api_url, api_username, api_password, api_insecure_skip_verify
    )

    debug = True if log_level == "debug" else False
    verbose = True if log_level == "warning" else False
    quiet = True if log_level == "warning" else False

    kopf.configure(
        debug=debug,
        verbose=verbose,
        quiet=quiet,
        log_format=kopf.LogFormat["FULL" if log_format == "text" else "JSON"],
    )

    kopf.run(
        standalone=True,
        clusterwide=True,
        liveness_endpoint=liveness_endpoint,
    )
