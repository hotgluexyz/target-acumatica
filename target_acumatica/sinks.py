"""Dynamic fallback handles each Singer stream as an Acumatica entity."""

from target_acumatica.client import AcumaticaRecordSink


def field_value(field):
    """Return a value from native or plain Acumatica JSON."""
    return field.get("value") if isinstance(field, dict) else field


def lines_match(payload_line, existing_line):
    """Match expense lines by description and inventory lines by item plus description."""
    description = field_value(payload_line.get("TransactionDescription"))
    inventory_id = field_value(payload_line.get("InventoryID"))
    if inventory_id:
        return (
            field_value(existing_line.get("InventoryID")) == inventory_id
            and field_value(existing_line.get("TransactionDescription")) == description
        )
    return field_value(existing_line.get("TransactionDescription")) == description


class BillSink(AcumaticaRecordSink):
    """Preserve Acumatica detail row identity when updating bills."""

    name = "Bill"

    def upsert_record(self, record, context):
        if record.get("id"):
            record.pop("Type", None)
            if record.get("Details"):
                self.set_detail_ids(record)
        return super().upsert_record(record, context)

    def set_detail_ids(self, record):
        response = self.request_api(
            "GET", f"{self.endpoint}/{record['id']}", params={"$expand": "Details"}
        )
        existing = response.json().get("Details", [])
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
                    and lines_match(line, current)
                ),
                None,
            )
            if match:
                line["id"] = match["id"]
                used.add(match["id"])


class EntitySink(AcumaticaRecordSink):
    """Accept native payloads for writable top-level endpoint entities."""
