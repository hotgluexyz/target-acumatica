# target-acumatica

Acumatica contract REST target scaffolded with the Hotglue target cookiecutter and built on `TargetHotglue` / `HotglueSink` from Hotglue Singer SDK 1.0.53.

Each Singer stream names a writable top-level Acumatica entity, such as `Vendor`, `Bill`, `Customer`, or `StockItem`. The target sends native Acumatica JSON with `PUT /entity/{endpoint_name}/{endpoint_version}/{entity}`. Endpoint availability and required fields depend on the Acumatica instance and its customizations. Actions, attachments, and read-only inquiries are outside this target's write interface.

## Configuration

```json
{
  "api_url": "https://example.com/Acumatica",
  "endpoint_name": "Default",
  "endpoint_version": "24.200.001",
  "client_id": "your-client-id",
  "client_secret": "your-client-secret",
  "refresh_token": "your-refresh-token"
}
```

`instance_url` is an alias for `api_url` and takes precedence. Optional settings: `token_url` (defaults to the instance's `/identity/connect/token`), `timeout` (seconds, default 60), `entity_mapping` (Singer stream → entity name), `branch`, and `business_date`. `access_token` can be used alone for short local tests. `expires_in` follows the SDK convention of an absolute Unix expiry, rather than a duration.

Use OAuth authorization code login with `api offline_access` and the registered redirect URI. A client ID and secret alone cannot authorize a user. Shared authentication across sinks prevents rotating the same refresh token concurrently. The SDK persists refreshed credentials locally or uses the Hotglue token service in hosted jobs. For local refresh, use a config file and set `_refresh_token_via_hg_api` to false.

## Payloads and snapshots

```json
{"type":"SCHEMA","stream":"Vendor","schema":{"type":"object","additionalProperties":true},"key_properties":["externalId"],"x-hotglue":{"target_state_fields":["VendorID"],"target_state_include_hash":true}}
{"type":"RECORD","stream":"Vendor","record":{"externalId":"airbase-vendor-id","VendorID":{"value":"AB001"},"VendorName":{"value":"Example"}}}
```

Scalars must use Acumatica's `{"value": ...}` representation. Nested entities and detail arrays remain native JSON. `externalId` belongs to Hotglue and is removed before HTTP requests. SDK snapshots retain destination IDs, source IDs, payload hashes, custom fields, errors, and success/update summaries. Subsequent changed records reuse the prior successful destination ID. Snapshot IDs do not change the source payload hash.

Use stable Acumatica natural keys for first-write retries, including retries after an uncertain network response. Existing detail rows need their Acumatica row IDs to update them; replacing or deleting detail collections requires an explicit mapping. The target does not infer accounting actions or release documents. HTTP 429/5xx and transient network errors use SDK backoff; validation and auth failures become failed record bookmarks. Always inspect target state, since SDK record failures may be captured without a nonzero process exit.

## Local use

Python 3.10:

```sh
python -m pip install -e . pytest ruff
pytest -q
ruff check target_acumatica tests
 target-acumatica --config /private/config.json < /private/input.singer > /private/target-state.json
```

Never commit credentials, OAuth callback URLs containing codes, or real input/state files. See the sibling `airbase-acumatica-etl` project for Airbase mapping.
