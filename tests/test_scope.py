"""Navigation-lockdown scope (policy layer only)."""

from navigator_mcp.core.scope import ScopeManager, host_matches


def test_host_matches():
    assert host_matches("example.com", "example.com")
    assert host_matches("*.example.com", "api.example.com")
    assert host_matches("*.example.com", "deep.sub.example.com")
    assert not host_matches("*.example.com", "example.com.org")
    assert not host_matches("example.com", "evil-example.com")
    # exact patterns include subdomains
    assert host_matches("example.com", "api.example.com")
    assert host_matches("EXAMPLE.COM", "example.com")  # case-insensitive


def test_no_lockdown_everything_allowed():
    sm = ScopeManager()
    ok, _ = sm.check("https://anything.anywhere/")
    assert ok


def test_lockdown_blocks_outside_hosts():
    sm = ScopeManager()
    sm.set_policy(["docs.python.org", "*.internal.test"])
    ok, _ = sm.check("https://docs.python.org/3/library/")
    assert ok
    ok, _ = sm.check("https://deep.service.internal.test/api")
    assert ok
    ok, reason = sm.check("https://public.example.com/")
    assert not ok and "policy" in reason


def test_subdomains_of_exact_pattern_allowed():
    sm = ScopeManager()
    sm.set_policy(["corp.internal"])
    ok, reason = sm.check("https://app.corp.internal/")
    assert ok, reason
    # suffix must dot-align: corp.internal.evil.com is NOT a subdomain
    ok, _ = sm.check("https://corp.internal.evil.com/")
    assert not ok


def test_empty_policy_is_noop():
    sm = ScopeManager()
    sm.set_policy([])
    assert not sm.policy_hosts
    ok, _ = sm.check("https://anything/")
    assert ok


def test_status_shape():
    sm = ScopeManager()
    sm.set_policy(["a.com", "b.com"])
    assert sm.status() == {
        "allowed_domains": ["a.com", "b.com"],
        "lockdown_active": True,
    }
