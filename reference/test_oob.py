"""OOB payload generation tests (parked with the security suite)."""

from oob import OOBSession


def test_oob_payload_format():
    session = OOBSession("oast.example")
    payload = session.generate_payload("Blind-SSRF_Test!")
    # tag cleaned to [a-z0-9]
    assert payload.startswith("blindssrftest.")
    # base domain = correlation+nonce . server
    assert payload.endswith("." + session.base_domain)
    assert session.base_domain.endswith(".oast.example")
    # deterministic per session
    assert payload == session.generate_payload("Blind-SSRF_Test!")


def test_oob_payload_empty_tag():
    session = OOBSession("oast.example")
    assert session.generate_payload("###").startswith("payload.")


def test_format_interactions_empty():
    assert "No new OOB interactions" in OOBSession.format_interactions([])


def test_format_interactions_report():
    out = OOBSession.format_interactions([
        {"protocol": "dns", "full-id": "taggy.abc.oast.io",
         "remote-address": "1.2.3.4", "raw-request": "IN A? taggy.abc.oast.io"}
    ])
    assert "[DNS]" in out
    assert "taggy" in out
    assert "1.2.3.4" in out
