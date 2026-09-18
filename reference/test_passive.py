"""Passive scanner rules."""

from navigator_mcp.security.passive import scan_headers, scan_text, scan_urls


def test_missing_security_headers():
    alerts = scan_headers({"content-type": "text/html"})
    texts = " ".join(alerts)
    assert "Content-Security-Policy" in texts
    assert "Strict-Transport-Security" in texts
    assert "clickjacking" in texts


def test_version_leak():
    alerts = scan_headers({"Server": "nginx/1.18.0", "X-Powered-By": "Express"})
    assert any("discloses technology" in a for a in alerts)


def test_cookie_flags():
    alerts = scan_headers({
        "set-cookie": "sid=abc123; Path=/",
        "content-security-policy": "default-src 'self'",
        "strict-transport-security": "max-age=31536000",
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "no-referrer",
    })
    cookie_alerts = [a for a in alerts if "cookie" in a.lower()]
    assert cookie_alerts and "not Secure" in cookie_alerts[0]


def test_wildcard_cors():
    alerts = scan_headers({"access-control-allow-origin": "*"})
    assert any("any origin" in a for a in alerts)


def test_secrets_detection():
    text = (
        "config: AKIAIOSFODNN7EXAMPLE and sk-proj-abc123defGHI456jklMNO789"
        "plus xoxb-1234567890abcdef"
    )
    alerts = scan_text(text)
    joined = " ".join(alerts)
    assert "AWS Access Key ID" in joined
    assert "API key" in joined
    assert "Slack token" in joined


def test_entropy_suppresses_false_positives():
    # low-entropy strings that match patterns loosely should not fire
    alerts = scan_text("the value sk-aaaaaaaaaaaaaaaaaaaa is a placeholder")
    assert not any("OpenAI" in a for a in alerts)


def test_jwt_and_private_key():
    alerts = scan_text(
        "token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    )
    assert any("JWT" in a for a in alerts)
    alerts = scan_text("-----BEGIN RSA PRIVATE KEY-----")
    assert any("Private key" in a for a in alerts)


def test_internal_ip_and_sql_error():
    alerts = scan_text("connect to 192.168.1.50 failed; SQL syntax error near WHERE")
    joined = " ".join(alerts)
    assert "Internal IP" in joined
    assert "SQL error" in joined


def test_emails_opt_in():
    text = "contact admin@example.com now"
    assert not any("Email" in a for a in scan_text(text))
    assert any("Email" in a for a in scan_text(text, include_emails=True))


def test_url_scanners():
    urls = [
        "http://insecure.example.com/script.js",  # mixed content
        "https://site.com/.git/config",
        "https://site.com/backup.sql",
        "https://api.site.com/swagger/index.html",
        "https://bucket.s3.amazonaws.com/file",
    ]
    alerts = scan_urls(urls, page_is_https=True)
    joined = " ".join(alerts)
    assert "Mixed content" in joined
    assert "source-control" in joined
    assert "Backup" in joined
    assert "documentation" in joined
    assert "S3 bucket" in joined


def test_no_false_positive_on_clean_page():
    clean_text = "Welcome to our store. Browse our catalog of fine products."
    alerts = scan_text(clean_text)
    assert alerts == []
