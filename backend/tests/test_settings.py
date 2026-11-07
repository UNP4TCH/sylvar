from app.core.security.config import SecurityConfigError
from app.main import build_verifier
from tests.settings_helpers import clean_settings


def test_allowed_origins_parsed_from_comma_separated() -> None:
    s = clean_settings(allowed_origins="http://a.test, https://b.test")
    assert s.allowed_origins_list == ["http://a.test", "https://b.test"]


def test_wildcard_origin_rejected() -> None:
    try:
        clean_settings(allowed_origins="http://a.test,*")
    except ValueError:
        return
    raise AssertionError("wildcard origin must be rejected")


def test_unconfigured_auth_yields_no_verifier_and_warns(caplog) -> None:  # type: ignore[no-untyped-def]
    s = clean_settings()
    assert s.jwt_config() is None
    with caplog.at_level("WARNING", logger="sylvar.startup"):
        assert build_verifier(s) is None
    assert "NOT configured" in caplog.text


def test_template_placeholder_env_is_treated_as_unconfigured() -> None:
    s = clean_settings(supabase_url="https://YOUR-PROJECT.supabase.co", jwt_audience="")
    assert build_verifier(s) is None


def test_partial_auth_configuration_fails_fast_at_startup() -> None:
    s = clean_settings(supabase_url="https://p.example.invalid")  # real URL, no audience
    try:
        build_verifier(s)
    except SecurityConfigError:
        return
    raise AssertionError("partial auth config must fail fast")


def test_configured_auth_logs_issuer_without_secrets(caplog) -> None:  # type: ignore[no-untyped-def]
    s = clean_settings(supabase_url="https://p.example.invalid", jwt_audience="aud")
    with caplog.at_level("INFO", logger="sylvar.startup"):
        build_verifier(s)
    assert "configured" in caplog.text and "p.example.invalid" in caplog.text


def test_configured_auth_builds_verifier_with_spec_default_ttl() -> None:
    s = clean_settings(supabase_url="https://p.example.invalid", jwt_audience="aud")
    cfg = s.jwt_config()
    assert cfg is not None and cfg.jwks_cache_ttl_seconds == 86400.0
    assert build_verifier(s) is not None


def test_insecure_issuer_fails_fast_at_startup() -> None:
    s = clean_settings(supabase_url="http://p.example.invalid", jwt_audience="aud")
    try:
        build_verifier(s)
    except SecurityConfigError:
        return
    raise AssertionError("http (non-localhost) issuer must be rejected")


def test_symmetric_algorithm_fails_fast_at_startup() -> None:
    s = clean_settings(supabase_url="https://p.example.invalid", jwt_audience="aud",
                       jwt_algorithms="HS256")
    try:
        build_verifier(s)
    except SecurityConfigError:
        return
    raise AssertionError("HS256 must be rejected")
