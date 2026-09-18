"""WAF fingerprinting from headers."""

from navigator_mcp.security.waf import detect_from_headers


def test_cloudflare():
    result = detect_from_headers(
        {"server": "cloudflare", "cf-ray": "8abc123"}, 200
    )
    assert result["detected"]
    assert result["wafs"][0]["waf"] == "Cloudflare"
    assert "Slow scans" in result["recommendation"]


def test_imperva():
    result = detect_from_headers({"x-iinfo": "abc"})
    assert result["detected"]
    assert "Imperva" in result["wafs"][0]["waf"]


def test_block_status_and_body_hints():
    result = detect_from_headers(
        {"server": "cloudflare"}, 403, "Attention Required! | Cloudflare"
    )
    assert result["block_status"]
    assert "Attention Required" in result["body_block_hints"]


def test_no_waf():
    result = detect_from_headers({"content-type": "text/html"}, 200)
    assert not result["detected"]
    assert "standard pacing" in result["recommendation"]


def test_aws_waf():
    result = detect_from_headers({"x-amz-cf-id": "xyz", "via": "1.1 CloudFront"})
    assert result["detected"]
    assert result["wafs"][0]["waf"] == "AWS WAF / CloudFront"
