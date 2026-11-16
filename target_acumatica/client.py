"""Shared HTTP sink for Acumatica contract-based REST PUT upserts."""

from __future__ import annotations

import copy
import re
from urllib.parse import urlsplit
import requests
from hotglue_etl_exceptions import InvalidCredentialsError, InvalidPayloadError
from hotglue_singer_sdk.exceptions import FatalAPIError
from hotglue_singer_sdk.target_sdk.client import HotglueSink


def identifier(value: str) -> str:
    """Only allow entity and endpoint identifiers, never arbitrary URL paths."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value):
        raise ValueError(f"Invalid Acumatica entity or endpoint name: {value!r}")
    return value


class AcumaticaRecordSink(HotglueSink):
    """Leave checkpointing, duplicate detection, and snapshots to the SDK."""

    unified_schema = None
    auto_validate_unified_schema = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.processed_hashes = []
        self.previous_state = None
        self.http_headers = {"Accept": "application/json"}
        self.params = {}
        self.session = requests.Session()
        self.timeout = int(self.config.get("timeout", 60))
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        identifier(self.entity)
        identifier(self.config.get("endpoint_name", "Default"))
        if not re.fullmatch(r"\d+\.\d+\.\d+", self.config.get("endpoint_version", "24.200.001")):
            raise ValueError("endpoint_version must have format 24.200.001")
        parsed = urlsplit(self.config["instance_url"])
        if (
            parsed.scheme not in ("https", "http")
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
            or parsed.username
        ):
            raise ValueError(
                "instance_url must be an HTTP(S) instance URL without credentials or query"
            )

    @property
    def name(self):
        return self.stream_name

    @property
    def entity(self):
        return self.config.get("entity_mapping", {}).get(self.stream_name, self.stream_name)

    @property
    def endpoint(self):
        return "/" + identifier(self.entity)

    @property
    def base_url(self):
        return "{}/entity/{}/{}".format(
            self.config["instance_url"].rstrip("/"),
            identifier(self.config.get("endpoint_name", "Default")),
            self.config.get("endpoint_version", "24.200.001"),
        )

    @property
    def authenticator(self):
        return self._target.acumatica_authenticator

    def _request(
        self, http_method, endpoint, params=None, request_data=None, headers=None, verify=True
    ):
        request_headers = dict(self.http_headers)
        request_headers.update(headers or {})
        request_headers.update(self.authenticator.auth_headers)
        if self.config.get("branch"):
            request_headers["PX-CbApiBranch"] = self.config["branch"]
        if self.config.get("business_date"):
            request_headers["PX-CbApiBusinessDate"] = self.config["business_date"]
        response = self.session.request(
            http_method,
            self.url(endpoint),
            params=dict(params or {}),
            json=request_data,
            headers=request_headers,
            timeout=self.timeout,
            verify=verify,
            allow_redirects=False,
        )
        self.validate_response(response)
        return response

    def validate_response(self, response):
        if response.status_code in (401, 403):
            raise InvalidCredentialsError(
                f"Acumatica authorization failed ({response.status_code})"
            )
        if 300 <= response.status_code < 400:
            raise FatalAPIError("Unexpected redirect; check the Acumatica instance URL")
        if 400 <= response.status_code < 500 and response.status_code != 429:
            raise InvalidPayloadError(
                f"Acumatica rejected {self.entity} ({response.status_code}): {response.text[:4000]}"
            )
        super().validate_response(response)

    def preprocess_record(self, record, context):
        payload = copy.deepcopy(record)
        # externalId is managed by Hotglue and never sent to Acumatica.
        external_id = context.get("acumatica_external_id")
        if external_id and not payload.get("id"):
            previous = self.get_previous_state() or {}
            matches = [
                s
                for s in previous.get("bookmarks", {}).get(self.name, [])
                if s.get("success") and s.get("externalId") == external_id and s.get("id")
            ]
            if matches:
                payload["id"] = matches[-1]["id"]
        return payload

    def process_record(self, record, context):
        context = dict(context)
        context["acumatica_external_id"] = record.get("externalId") or record.get("externalid")
        return super().process_record(record, context)

    def build_record_hash(self, record):
        # Snapshot IDs are transport metadata, not changes to the source payload.
        payload = dict(record)
        if payload.get("externalId") or payload.get("externalid"):
            payload.pop("id", None)
        return super().build_record_hash(payload)

    def upsert_record(self, record, context):
        response = self.request_api("PUT", self.endpoint, request_data=record)
        result = response.json()
        if not isinstance(result, dict) or not result.get("id"):
            raise InvalidPayloadError(
                "Acumatica returned no entity id; cannot acknowledge the write"
            )
        return result["id"], True, {"is_updated": bool(record.get("id"))}
