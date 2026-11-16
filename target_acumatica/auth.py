"""OAuth refresh uses the SDK's token rotation and config persistence."""

from hotglue_singer_sdk.helpers._util import utc_now
from hotglue_singer_sdk.target_sdk.auth import OAuthAuthenticator


class AcumaticaAuthenticator(OAuthAuthenticator):
    """Share one authenticator across sinks to avoid refresh-token reuse."""

    def is_token_valid(self) -> bool:
        if not self._config.get("access_token"):
            return False
        if not self._config.get("refresh_token"):
            expiry = self._config.get("expires_in")
            if expiry and int(expiry) <= int(utc_now().timestamp()) + 120:
                raise ValueError("Access token expired; authorize again or supply refresh_token")
            return True
        return super().is_token_valid()
