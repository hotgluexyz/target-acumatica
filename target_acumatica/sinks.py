# Copyright (c) 2026 Hotglue
"""Acumatica target sink class, which handles writing streams."""

from __future__ import annotations

from target_acumatica.client import AcumaticaRecordSink


def _field_value(field: dict | str | None) -> str | None:
    if isinstance(field, dict):
        return field.get("value")
    return field


def _lines_match(payload_line: dict, existing_line: dict) -> bool:
    """Match an item line on InventoryID and Description, an expense line on Description."""
    description = _field_value(payload_line.get("TransactionDescription"))
    inventory_id = _field_value(payload_line.get("InventoryID"))
    if inventory_id:
        return (
            _field_value(existing_line.get("InventoryID")) == inventory_id
            and _field_value(existing_line.get("TransactionDescription")) == description
        )
    return _field_value(existing_line.get("TransactionDescription")) == description


class BillSink(AcumaticaRecordSink):
    """Bill sink. On update, drop Type and copy existing detail ids onto matching lines."""

    name = "Bill"

    @property
    def endpoint(self) -> str:
        return "/Bill"

    def upsert_record(self, record: dict, context: dict) -> tuple[str | None, bool, dict]:
        if record.get("id"):
            record.pop("Type", None)
            if record.get("Details"):
                self._set_detail_ids(record)
        return super().upsert_record(record, context)

    def _set_detail_ids(self, record: dict) -> None:
        response = self.request_api(
            "GET",
            f"{self.endpoint}/{record['id']}",
            params={"$expand": "Details"},
        )
        existing = response.json()["Details"]
        used = {line["id"] for line in record["Details"] if line.get("id")}
        for line in record["Details"]:
            if line.get("id"):
                continue
            match = next(
                (
                    current
                    for current in existing
                    if current.get("id")
                    and current["id"] not in used
                    and _lines_match(line, current)
                ),
                None,
            )
            if match is None:
                continue
            line["id"] = match["id"]
            used.add(match["id"])


class FallbackSink(AcumaticaRecordSink):
    """Fallback sink implementation."""

    stream_name = "Fallback"

    @property
    def name(self) -> str:
        return self.stream_name

    @property
    def endpoint(self) -> str:
        return f"/{self.stream_name}"
