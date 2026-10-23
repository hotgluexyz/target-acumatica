# Copyright (c) 2026 Hotglue
"""Acumatica target class."""

from __future__ import annotations

from functools import cached_property

from hotglue_singer_sdk import typing as th
from hotglue_singer_sdk.target_sdk.target import TargetHotglue

from target_acumatica.auth import AcumaticaAuthenticator
from target_acumatica.client import fetch_default_endpoint_version, instance_url
from target_acumatica.sinks import BillSink, FallbackSink


class TargetAcumatica(TargetHotglue):
    """Target for Acumatica."""

    name = "target-acumatica"
    SINK_TYPES = [BillSink]

    config_jsonschema = th.PropertiesList(
        th.Property(
            "api_url",
            th.StringType(),
            required=True,
            description="Acumatica site URL, such as http://host/AcumaticaSandbox",
        ),
        th.Property(
            "client_id",
            th.StringType(),
            required=True,
            description="Client identifier for the token endpoint",
        ),
        th.Property(
            "client_secret",
            th.StringType(),
            required=True,
            description="Client secret for the token endpoint",
        ),
        th.Property(
            "refresh_token",
            th.StringType,
            required=True,
            description="Refresh token used to obtain new access tokens",
        ),
        th.Property(
            "access_token",
            th.StringType,
            required=False,
            description="Current access token (usually populated after refresh)",
        ),
        th.Property(
            "expires_in",
            th.IntegerType,
            required=False,
            description="Epoch seconds when the access token expires (updated on refresh)",
        ),
    ).to_dict()

    default_sink_class = FallbackSink

    @cached_property
    def default_endpoint_version(self) -> str:
        """Return the latest Default endpoint version, fetched once per target."""
        return fetch_default_endpoint_version(self.config["api_url"])

    @classmethod
    def access_token_support(
        cls,
        connector: TargetHotglue | None = None,
    ) -> tuple[type[AcumaticaAuthenticator], str]:
        """Return the authenticator class and OAuth token endpoint.

        Returns:
            A tuple with the authenticator class and the OAuth token endpoint URL.
        """
        if connector is None:
            return AcumaticaAuthenticator, ""
        return (
            AcumaticaAuthenticator,
            f"{instance_url(connector.config['api_url'])}/identity/connect/token",
        )


if __name__ == "__main__":
    TargetAcumatica.cli()
