# target-acumatica

`target-acumatica` is a Singer target for **Acumatica**, built with the [Hotglue Singer SDK](https://github.com/hotgluexyz/HotglueSingerSDK) (`TargetHotglue`, HTTP sinks, SDK authenticators).

This project was generated from the Hotglue target cookiecutter with:

| Option | Value |
|--------|--------|
| `auth_method` | `OAuth2` |
| `sinks` | `Fallback | record` |
| `api_url` | required site URL; entity base is `{api_url}/entity/Default/{version}` |

## Project layout

| Path | Role |
|------|------|
| `target_acumatica/target.py` | `TargetAcumatica` — config schema, `SINK_TYPES`, optional `default_sink_class` and `access_token_support` |
| `target_acumatica/client.py` | `AcumaticaSink` base class, `RecordSink` / `BatchSink` stubs, `authenticator` |
| `target_acumatica/sinks.py` | Per-stream sink classes (`FallbackSink` or named `*Sink` classes) |
| `target_acumatica/auth.py` | Present only when generated with **OAuth2** (removed by cookiecutter hook otherwise) |
| `.secrets/config.json` | Sample config matching your `auth_method` |

## Configuration

Settings are defined in `config_jsonschema` on `TargetAcumatica` in `target_acumatica/target.py`.
For this project (**OAuth2**), config includes: `api_url`, `client_id`, `client_secret`, `refresh_token`, and optional `access_token` / `expires_in`.

Inspect the live schema:

```bash
target-acumatica --about
target-acumatica --about --format=markdown
```

Local secrets: edit `.secrets/config.json` (shape matches `auth_method` above).

## Authentication

| `auth_method` | Implementation |
|---------------|----------------|
| **OAuth2** | `AcumaticaAuthenticator` in `auth.py`; `TargetAcumatica.access_token_support()` returns the authenticator class and `{api_url}/identity/connect/token`. |
| **Bearer Token** | `BearerTokenAuthenticator` in `client.py` |
| **Basic Auth** | `BasicAuthenticator` with `username` / `password` |
| **API Key** | `ApiAuthenticator` with configurable header name/prefix |

HTTP calls use `{api_url}/entity/Default/{version}`, where `version` is the newest `Default` contract published at `{api_url}/entity`.

## Sinks

Sinks are declared at scaffold time as `StreamName | record` or `StreamName | batch`, comma-separated.

Generated with: `Fallback | record`
**Fallback mode:** `FallbackSink` in `sinks.py` handles any stream dynamically (`name` / `endpoint` from `stream_name`). `target.py` sets `default_sink_class = FallbackSink` and leaves `SINK_TYPES` empty.

Shared HTTP behavior lives in `client.py` (`AcumaticaRecordSink` / `AcumaticaBatchSink` as generated).

## Usage

```bash
target-acumatica --version
target-acumatica --help
tap-smoke-test | target-acumatica --config /path/to/config.json
```

## Developer setup

Prerequisites: Python 3.10+, [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pytest
uv run target-acumatica --help
tox -e lint    # ruff check + format
```

For implementation notes and conventions, see `AGENTS.md` (or `CLAUDE.md` if that was selected at generation).

## References

- [Hotglue Singer SDK](https://github.com/hotgluexyz/HotglueSingerSDK)
