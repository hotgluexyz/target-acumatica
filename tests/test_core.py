"""Exercise actual SDK processing, state, HTTP errors, and OAuth rotation."""

import json
from io import StringIO
from unittest.mock import Mock

import pytest
import requests
from hotglue_etl_exceptions import InvalidCredentialsError
from hotglue_singer_sdk.exceptions import RetriableAPIError

from target_acumatica.target import TargetAcumatica


def response(code=200, body=None):
    result = requests.Response()
    result.status_code = code
    result._content = json.dumps(body or {"id": "destination-1"}).encode()
    result.url = "https://acumatica.test/entity/Default/24.200.001/Vendor"
    return result


@pytest.fixture
def target(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    instance = TargetAcumatica(
        config={"instance_url": "https://acumatica.test", "access_token": "test"}
    )
    instance.incremental_target_state_path = str(tmp_path / "state.json")
    yield instance
    instance._shutdown_requested.set()


def sink(target, name="Vendor"):
    return target.get_sink(name, schema={"type": "object", "properties": {}}, key_properties=[])


def test_put_and_sdk_bookmarks(target):
    s = sink(target)
    s.session.request = Mock(return_value=response())
    s.configure_target_state_custom_data(
        {"target_state_fields": ["VendorID"], "target_state_include_hash": True}
    )
    record = {
        "externalId": "source-1",
        "VendorID": {"value": "AB123"},
        "VendorName": {"value": "Test"},
    }
    s.process_record(dict(record), {})
    s.process_record(dict(record), {})
    assert s.session.request.call_count == 1
    args, kwargs = s.session.request.call_args
    assert args == ("PUT", "https://acumatica.test/entity/Default/24.200.001/Vendor")
    assert "externalId" not in kwargs["json"]
    assert kwargs["headers"]["Authorization"] == "Bearer test"
    state = s.latest_state
    assert state["summary"]["Vendor"] == {"success": 1, "fail": 0, "updated": 0, "existing": 1}
    assert state["bookmarks"]["Vendor"][0]["externalId"] == "source-1"
    assert state["bookmarks"]["Vendor"][0]["customData"]["VendorID"] == {"value": "AB123"}


def test_failed_record_is_bookmarked(target):
    s = sink(target)
    s.session.request = Mock(return_value=response(422, {"message": "Vendor class required"}))
    s.process_record({"externalId": "source-2", "VendorName": {"value": "Test"}}, {})
    state = s.latest_state["bookmarks"]["Vendor"][0]
    assert state["success"] is False
    assert state["externalId"] == "source-2"
    assert "422" in state["error"]
    assert state["hg_error_class"] == "InvalidPayloadError"


def test_snapshot_id_reused(target):
    path = target.incremental_target_state_path
    with open(path, "w") as f:
        json.dump(
            {
                "bookmarks": {
                    "Vendor": [{"externalId": "source-1", "id": "previous-id", "success": True}]
                },
                "summary": {"Vendor": {"success": 1, "fail": 0, "existing": 0, "updated": 0}},
            },
            f,
        )
    s = sink(target)
    s.session.request = Mock(return_value=response())
    s.process_record({"externalId": "source-1", "VendorName": {"value": "Changed"}}, {})
    assert s.session.request.call_args.kwargs["json"]["id"] == "previous-id"
    assert s.latest_state["summary"]["Vendor"]["updated"] == 1


def test_dynamic_entities_and_auth_shared(target):
    vendor_sink = sink(target)
    bill_sink = sink(target, "Bill")
    assert bill_sink.endpoint == "/Bill"
    assert vendor_sink.authenticator is bill_sink.authenticator
    assert vendor_sink.processed_hashes is not bill_sink.processed_hashes
    with pytest.raises(ValueError, match="Invalid Acumatica"):
        sink(target, "../identity")


def test_retry_classification(target):
    s = sink(target)
    for status in [429, 500, 503]:
        with pytest.raises(RetriableAPIError):
            s.validate_response(response(status))
    with pytest.raises(InvalidCredentialsError):
        s.validate_response(response(401))


def test_refresh_rotates_and_persists(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "instance_url": "https://acumatica.test",
                "client_id": "client",
                "client_secret": "secret",
                "refresh_token": "old",
                "_refresh_token_via_hg_api": False,
            }
        )
    )
    t = TargetAcumatica(config=str(path))
    mock = Mock(
        return_value=response(
            200, {"access_token": "access", "refresh_token": "rotated", "expires_in": 3600}
        )
    )
    monkeypatch.setattr(requests, "post", mock)
    assert t.acumatica_authenticator.auth_headers == {"Authorization": "Bearer access"}
    assert t.acumatica_authenticator.auth_headers == {"Authorization": "Bearer access"}
    assert mock.call_count == 1
    assert json.loads(path.read_text())["refresh_token"] == "rotated"
    t._shutdown_requested.set()


def test_actual_singer_listen(target, monkeypatch):
    monkeypatch.setattr(requests.Session, "request", Mock(return_value=response()))
    messages = [
        {
            "type": "SCHEMA",
            "stream": "Vendor",
            "schema": {
                "type": "object",
                "properties": {"externalId": {"type": "string"}, "VendorName": {"type": "object"}},
            },
            "key_properties": ["externalId"],
        },
        {
            "type": "RECORD",
            "stream": "Vendor",
            "record": {"externalId": "s1", "VendorName": {"value": "Test"}},
        },
    ]
    target.listen(StringIO("\n".join(json.dumps(m) for m in messages)))
    assert target._latest_state["summary"]["Vendor"]["success"] == 1


def test_snapshot_identity_does_not_change_payload_hash(target):
    s = sink(target)
    record = {"externalId": "source-1", "VendorName": {"value": "Name"}}
    assert s.build_record_hash(record) == s.build_record_hash({**record, "id": "snapshot-id"})


def test_hotglue_api_url_alias():
    t = TargetAcumatica(config={"api_url": "https://acumatica.test", "access_token": "test"})
    assert t.config["instance_url"] == "https://acumatica.test"
    assert t.access_token_support(t)[1] == "https://acumatica.test/identity/connect/token"
    t._shutdown_requested.set()
