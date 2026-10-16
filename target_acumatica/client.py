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


_UNWRAPPED_KEYS = {
    "id",
    "custom",
}


def _wrap_field(value: Any) -> Any:
    """Return an Acumatica field, or None when the value should be omitted."""
    if value is None:
        converted = None
    elif isinstance(value, list):
        converted = []
        for item in value:
            item_value = _wrap_field(item)
            if item_value is not None and item_value != {}:
                converted.append(item_value)
    elif isinstance(value, dict) and set(value) <= {"value", "error"}:
        converted = None if value.get("value") is None and "error" not in value else value
    elif isinstance(value, dict) and set(value) <= {"id", "description"} and "id" in value:
        converted = {"value": value}
    elif isinstance(value, dict):
        converted = _to_acumatica_entity(value)
    else:
        converted = {"value": value}
    return converted


def _to_acumatica_entity(record: dict) -> dict:
    """Wrap plain record fields into Acumatica ``{"value": ...}`` objects."""
    wrapped: dict[str, Any] = {}
    for key, value in record.items():
        if key in _UNWRAPPED_KEYS:
            if value is not None:
                wrapped[key] = value
            continue
        converted = _wrap_field(value)
        if converted is not None:
            wrapped[key] = converted
    return wrapped


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

    def __init__(
        self,
        target: Any,
        stream_name: str,
        schema: dict,
        key_properties: list[str] | None,
    ) -> None:
        """Build one authenticator and reuse it for every request from this sink."""
        super().__init__(target, stream_name, schema, key_properties)
        authenticator_class, auth_endpoint = target.access_token_support(target)
        self.authenticator = authenticator_class(target, self.auth_state, auth_endpoint)

    @property
    def base_url(self) -> str:
        """Return the Default entity URL for the configured Acumatica site."""
        root = instance_url(self.config["api_url"])
        version = self._target.default_endpoint_version
        return f"{root}/entity/Default/{version}"


class AcumaticaRecordSink(AcumaticaSink, HotglueSink):
    """Acumatica Record target sink class for record sinks."""

    name = "AcumaticaRecordSink"

    def preprocess_record(self, record: dict, _context: dict) -> dict:
        return _to_acumatica_entity(record)

    def upsert_record(self, record: dict, _context: dict) -> tuple[str | None, bool, dict]:
        """Create with PUT. PATCH when ``id`` is set so only the sent fields change."""
        state_updates = {}
        method = "PUT"
        if record.get("id"):
            method = "PATCH"
            state_updates["updated"] = True
        # Acumatica ignores detail collections in the body unless they are named here.
        expand = [name for name, value in record.items() if isinstance(value, list)]
        params = {"$expand": ",".join(expand)} if expand else {}
        response = self.request_api(method, self.endpoint, params=params, request_data=record)
        return response.json().get("id"), True, state_updates
