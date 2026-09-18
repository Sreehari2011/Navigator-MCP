"""Captcha sitekey extraction (no network)."""

from navigator_mcp.captcha.detector import extract_sitekey_from_html


def test_sitekey_extraction():
    # (data-sitekey extraction happens in-page; regex path covers JS configs)
    js = 'recaptcha: {sitekey: "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"}'
    assert extract_sitekey_from_html(js) == "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"
    assert extract_sitekey_from_html("nothing here") is None
