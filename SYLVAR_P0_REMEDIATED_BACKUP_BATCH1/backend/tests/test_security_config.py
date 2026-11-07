from app.core.security.config import SecurityConfigError, build_jwt_config


def _build(**kw):  # type: ignore[no-untyped-def]
    base = {
        "supabase_url": "https://p.example.invalid",
        "jwt_issuer": None,
        "jwt_audience": "aud",
        "jwks_url": None,
        "algorithms_csv": "ES256,RS256",
    }
    base.update(kw)
    return build_jwt_config(**base)


def _raises(fn) -> bool:  # type: ignore[no-untyped-def]
    try:
        fn()
    except SecurityConfigError:
        return True
    return False


def test_fully_unconfigured_returns_none() -> None:
    assert _build(supabase_url=None, jwt_issuer=None, jwt_audience=None, jwks_url=None) is None
    assert _build(supabase_url="", jwt_audience="  ") is None


def test_template_placeholders_count_as_unset() -> None:
    assert _build(supabase_url="https://YOUR-PROJECT.supabase.co", jwt_audience="") is None
    assert _build(supabase_url="https://YOUR-PROJECT.supabase.co", jwt_audience="CHANGE_ME") is None


def test_partial_configuration_fails_fast_not_silently_disabled() -> None:
    assert _raises(lambda: _build(jwt_audience=None))  # real URL but no audience
    assert _raises(lambda: _build(supabase_url=None, jwt_issuer=None))  # audience but no issuer source
    assert _raises(lambda: _build(supabase_url=None, jwt_issuer=None, jwt_audience=None,
                                  jwks_url="https://k.example.invalid/jwks"))


def test_derives_issuer_and_jwks_from_supabase_url() -> None:
    cfg = _build(supabase_url="https://p.example.invalid/")
    assert cfg is not None
    assert cfg.issuer == "https://p.example.invalid/auth/v1"
    assert cfg.jwks_url == "https://p.example.invalid/auth/v1/.well-known/jwks.json"


def test_explicit_values_override_derivation() -> None:
    cfg = _build(jwt_issuer="https://idp.example.invalid/x", jwks_url="https://idp.example.invalid/k")
    assert cfg is not None and cfg.issuer.endswith("/x") and cfg.jwks_url.endswith("/k")


def test_insecure_urls_rejected_except_localhost() -> None:
    assert _raises(lambda: _build(supabase_url="http://p.example.invalid"))
    assert _build(supabase_url="http://localhost:54321") is not None


def test_symmetric_and_none_algorithms_rejected() -> None:
    for bad in ("HS256", "none", "ES256,HS256", ""):
        assert _raises(lambda b=bad: _build(algorithms_csv=b))


def test_bad_numeric_bounds_rejected() -> None:
    assert _raises(lambda: _build(leeway_seconds=-1))
    assert _raises(lambda: _build(leeway_seconds=301))
    assert _raises(lambda: _build(jwks_cache_ttl_seconds=0))


def test_default_cache_ttl_matches_spec_24h() -> None:
    cfg = _build()
    assert cfg is not None and cfg.jwks_cache_ttl_seconds == 86400.0
