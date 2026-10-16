# Copyright (c) 2026 Hotglue
"""Authentication helpers for Acumatica."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hotglue_singer_sdk.target_sdk.auth import OAuthAuthenticator

if TYPE_CHECKING:
    from hotglue_singer_sdk.target_sdk.target import TargetHotglue


class AcumaticaAuthenticator(OAuthAuthenticator):
    """OAuth 2.0 refresh-token authenticator for Acumatica."""

    def __init__(
        self,
        target: TargetHotglue,
        state: dict[str, Any],
        auth_endpoint: str | None = None,
    ) -> None:
        """Initialize the authenticator.

        Args:
            target: The Singer target instance.
            state: Authentication state.
            auth_endpoint: Token endpoint URL (from ``target.access_token_support``).
        """
        super().__init__(target, state, auth_endpoint=auth_endpoint)

    @property
    def oauth_request_body(self) -> dict:
        """OAuth request body for the refresh-token grant."""
        return {
            "refresh_token": self._config["refresh_token"],
            "grant_type": "refresh_token",
            "client_id": self._config["client_id"],
            "client_secret": self._config["client_secret"],
        }
