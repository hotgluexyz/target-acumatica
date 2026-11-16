"""Dynamic fallback handles each Singer stream as an Acumatica entity."""

from target_acumatica.client import AcumaticaRecordSink


class EntitySink(AcumaticaRecordSink):
    """Accept native payloads for writable top-level endpoint entities."""
