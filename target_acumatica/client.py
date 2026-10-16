# Copyright (c) 2026 Hotglue
"""HTTP client and sink base classes for Acumatica."""

from __future__ import annotations

from typing import Any, ClassVar

import requests
from hotglue_singer_sdk.target_sdk.client import HotglueBaseSink, HotglueSink


def instance_url(api_url: str) -> str:
    """Return the Acumatica site root, ignoring a trailing slash."""
    return api_url.rstrip("/")


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def fetch_default_endpoint_version(api_url: str) -> str:
    """Return the newest ``Default`` contract version published at ``/entity``."""
    root = instance_url(api_url)
    response = requests.get(f"{root}/entity", timeout=300)
    response.raise_for_status()
    versions = [
        endpoint["version"]
        for endpoint in response.json()["endpoints"]
        if endpoint["name"] == "Default"
    ]
    return max(versions, key=_version_key)


class AcumaticaSink(HotglueBaseSink):
    """Acumatica Base target sink class for sinks."""

    auth_state: ClassVar[dict[str, Any]] = {}

    @property
    def base_url(self) -> str:
        """Return the Default entity URL for the configured Acumatica site."""
        root = instance_url(self.config["api_url"])
        version = self._target.default_endpoint_version
        return f"{root}/entity/Default/{version}"

    @property
    def authenticator(self) -> Any:
        authenticator, auth_endpoint = self._target.access_token_support(self._target)
        return authenticator(self._target, self.auth_state, auth_endpoint)


class AcumaticaRecordSink(AcumaticaSink, HotglueSink):
    """Acumatica Record target sink class for record sinks."""

    name = "AcumaticaRecordSink"

    def preprocess_record(self, record: dict, _context: dict) -> dict:
        return record

    def upsert_record(self, record: dict, _context: dict) -> None:
        state_updates = {}
        pk_field = self.key_properties[0] if self.key_properties else "id"
        pk = record.get(pk_field)
        method = "POST"
        endpoint = self.endpoint

        if pk:
            method = "PATCH"
            endpoint = f"{endpoint}{pk}"
            state_updates["updated"] = True

        response = self.request_api(method, endpoint, request_data=record)
        record_id = pk or response.json().get("id")
        return record_id, True, state_updates
