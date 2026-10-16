# Copyright (c) 2026 Hotglue
"""Acumatica target sink class, which handles writing streams."""

from __future__ import annotations

from target_acumatica.client import AcumaticaRecordSink


class FallbackSink(AcumaticaRecordSink):
    """Fallback sink implementation."""

    stream_name = "Fallback"

    @property
    def name(self) -> str:
        return self.stream_name

    @property
    def endpoint(self) -> str:
        return f"/{self.stream_name}"
