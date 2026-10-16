# Copyright (c) 2026 Hotglue
"""HTTP client and sink base classes for Acumatica."""

from __future__ import annotations

import json
from datetime import datetime
from functools import cache
from pathlib import Path
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


_DATE_ONLY_REF = "#/components/schemas/DateOnlyValue"


@cache
def _openapi_schemas() -> dict[str, Any]:
    path = Path(__file__).with_name("acumatica-openapi.json")
    document = json.loads(path.read_text())
    return document["components"]["schemas"]


def _ref_name(schema: dict | None) -> str | None:
    if not schema:
        return None
    ref = schema.get("$ref")
    if isinstance(ref, str):
        return ref.rsplit("/", 1)[-1]
    for option in schema.get("anyOf", []):
        name = _ref_name(option)
        if name:
            return name
    return None


@cache
def _schema_properties(name: str) -> dict[str, Any] | None:
    """Return the OpenAPI properties for an entity, or None when it is not in the schema."""
    schema = _openapi_schemas().get(name)
    if schema is None:
        return None
    properties: dict[str, Any] = {}
    for part in schema.get("allOf", []):
        ref_name = _ref_name(part)
        if ref_name:
            nested = _schema_properties(ref_name)
            if nested:
                properties.update(nested)
        properties.update(part.get("properties", {}))
    properties.update(schema.get("properties", {}))
    return properties


def _is_date_only(field_schema: dict | None) -> bool:
    return bool(field_schema) and field_schema.get("$ref") == _DATE_ONLY_REF


def _as_date(value: Any) -> Any:
    """Return the date portion of a date-only Acumatica field."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, str) and "T" in value:
        return value.split("T", 1)[0]
    return value


def _is_scalar_object(value: dict) -> bool:
    if set(value) <= {"value", "error"}:
        return True
    return set(value) <= {"id", "description"} and "id" in value


def _wrap_list(value: list, field_schema: dict | None) -> list:
    nested_name = _ref_name((field_schema or {}).get("items"))
    nested_properties = _schema_properties(nested_name) if nested_name else None
    converted = []
    for item in value:
        if isinstance(item, dict) and not _is_scalar_object(item):
            item_value = _to_acumatica_entity(item, nested_properties)
        else:
            item_value = _wrap_field(item, field_schema)
        if item_value is not None and item_value != {}:
            converted.append(item_value)
    return converted


def _wrap_value_object(value: dict, field_schema: dict | None) -> dict | None:
    if value.get("value") is None and "error" not in value:
        return None
    if not _is_date_only(field_schema):
        return value
    temporal = _as_date(value.get("value"))
    if temporal == value.get("value"):
        return value
    return {**value, "value": temporal}


def _wrap_field(value: Any, field_schema: dict | None = None) -> Any:
    """Return an Acumatica field, or None when the value should be omitted."""
    if value is None:
        converted = None
    elif isinstance(value, list):
        converted = _wrap_list(value, field_schema)
    elif isinstance(value, dict) and set(value) <= {"value", "error"}:
        converted = _wrap_value_object(value, field_schema)
    elif isinstance(value, dict) and set(value) <= {"id", "description"} and "id" in value:
        converted = {"value": value}
    elif isinstance(value, dict):
        nested_name = _ref_name(field_schema)
        nested_properties = _schema_properties(nested_name) if nested_name else None
        converted = _to_acumatica_entity(value, nested_properties)
    elif _is_date_only(field_schema):
        converted = {"value": _as_date(value)}
    else:
        converted = {"value": value}
    return converted


def _to_acumatica_entity(record: dict, properties: dict[str, Any] | None = None) -> dict:
    """Wrap plain record fields into Acumatica ``{"value": ...}`` objects."""
    wrapped: dict[str, Any] = {}
    for key, value in record.items():
        if key in _UNWRAPPED_KEYS:
            if value is not None:
                wrapped[key] = value
            continue
        field_schema = properties.get(key) if properties else None
        converted = _wrap_field(value, field_schema)
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
        return _to_acumatica_entity(record, _schema_properties(self.name))

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
