"""Acumatica contract-based REST target using Hotglue state snapshots."""

from __future__ import annotations

from hotglue_singer_sdk import typing as th
from hotglue_singer_sdk.target_sdk.target import TargetHotglue
from target_acumatica.auth import AcumaticaAuthenticator
from target_acumatica.sinks import EntitySink


class TargetAcumatica(TargetHotglue):
    """Load any writable top-level entity exposed by an Acumatica endpoint."""

    name = "target-acumatica"
    SINK_TYPES = []
    MAX_PARALLELISM = 1
    default_sink_class = EntitySink
    config_jsonschema = th.PropertiesList(
        th.Property("instance_url", th.StringType),
        th.Property("api_url", th.StringType, description="Hotglue instance URL alias"),
        th.Property("endpoint_name", th.StringType, default="Default"),
        th.Property("endpoint_version", th.StringType, default="24.200.001"),
        th.Property("client_id", th.StringType),
        th.Property("client_secret", th.StringType),
        th.Property("refresh_token", th.StringType),
        th.Property("access_token", th.StringType),
        th.Property("expires_in", th.IntegerType),
        th.Property("token_url", th.StringType),
        th.Property("timeout", th.IntegerType, default=60),
        th.Property("entity_mapping", th.ObjectType()),
        th.Property("branch", th.StringType),
        th.Property("business_date", th.StringType),
    ).to_dict()

    for _secret in ("client_secret", "refresh_token", "access_token"):
        config_jsonschema["properties"][_secret]["writeOnly"] = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._config["instance_url"] = self.config.get("instance_url") or self.config.get("api_url")
        if not self.config.get("instance_url"):
            raise ValueError("Supply instance_url or api_url")
        if not self.config.get("refresh_token") and not self.config.get("access_token"):
            raise ValueError("Supply refresh_token or access_token after OAuth authorization")
        if self.config.get("refresh_token") and not all(
            self.config.get(key) for key in ("client_id", "client_secret")
        ):
            raise ValueError("Refreshing tokens requires client_id and client_secret")
        self.acumatica_authenticator = AcumaticaAuthenticator(
            self, {}, self.access_token_support(self)[1]
        )

    @classmethod
    def access_token_support(cls, connector=None):
        config = connector.config if connector else {}
        token_url = config.get("token_url") or (
            (config.get("instance_url") or config.get("api_url") or "").rstrip("/")
            + "/identity/connect/token"
        )
        return AcumaticaAuthenticator, token_url


if __name__ == "__main__":
    TargetAcumatica.cli()
