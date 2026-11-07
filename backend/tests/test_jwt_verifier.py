import asyncio
import base64
import json
import time

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

from tests.jwt_helpers import (
    AUDIENCE,
    ISSUER,
    USER_ID,
    FakeClock,
    FakeJWKS,
    TestKey,
    ec_p256_public_jwk,
    expect_auth_error,
    make_verifier,
    run,
)

EC = TestKey("kid-ec", "EC")
RSA = TestKey("kid-rsa", "RSA")


def test_valid_es256_resolves_user_id() -> None:
    v = make_verifier(FakeJWKS(EC, RSA))
    user = run(v.verify(EC.token()))
    assert str(user.user_id) == USER_ID


def test_valid_rs256_resolves_user_id() -> None:
    v = make_verifier(FakeJWKS(EC, RSA))
    assert str(run(v.verify(RSA.token())).user_id) == USER_ID


def test_expired_token_rejected() -> None:
    v = make_verifier(FakeJWKS(EC))
    expect_auth_error(v.verify(EC.token(exp=int(time.time()) - 10)), "TOKEN_EXPIRED")


def test_leeway_allows_slightly_expired() -> None:
    v = make_verifier(FakeJWKS(EC), leeway_seconds=30)
    assert run(v.verify(EC.token(exp=int(time.time()) - 5)))


def test_wrong_issuer_rejected() -> None:
    v = make_verifier(FakeJWKS(EC))
    expect_auth_error(v.verify(EC.token(iss="https://evil.invalid/auth/v1")), "TOKEN_INVALID")


def test_wrong_audience_rejected() -> None:
    v = make_verifier(FakeJWKS(EC))
    expect_auth_error(v.verify(EC.token(aud="someone-else")), "TOKEN_INVALID")


def test_missing_required_claims_rejected() -> None:
    v = make_verifier(FakeJWKS(EC))
    for claim in ("exp", "sub", "iss", "aud"):
        expect_auth_error(v.verify(EC.token(**{claim: None})), "TOKEN_INVALID")


def test_non_uuid_subject_rejected() -> None:
    v = make_verifier(FakeJWKS(EC))
    expect_auth_error(v.verify(EC.token(sub="not-a-uuid")), "TOKEN_INVALID")


def test_tampered_signature_rejected() -> None:
    v = make_verifier(FakeJWKS(EC))
    head, payload, sig = EC.token().split(".")
    forged = json.loads(base64.urlsafe_b64decode(payload + "=="))
    forged["sub"] = "99999999-2222-4333-8444-555555555555"
    new_payload = base64.urlsafe_b64encode(json.dumps(forged).encode()).rstrip(b"=").decode()
    expect_auth_error(v.verify(f"{head}.{new_payload}.{sig}"), "TOKEN_INVALID")


def test_token_signed_by_other_key_same_kid_rejected() -> None:
    impostor = TestKey("kid-ec", "EC")  # same kid, different key material
    v = make_verifier(FakeJWKS(EC))
    expect_auth_error(v.verify(impostor.token()), "TOKEN_INVALID")


def test_alg_none_rejected() -> None:
    v = make_verifier(FakeJWKS(EC))
    token = jwt.encode(
        {"sub": USER_ID, "iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 60},
        key=None, algorithm="none", headers={"kid": "kid-ec"},
    )
    expect_auth_error(v.verify(token), "TOKEN_INVALID")


def test_hs256_algorithm_confusion_rejected() -> None:
    v = make_verifier(FakeJWKS(RSA))
    # Attacker signs with HS256 using an arbitrary shared secret (e.g. derived from public data).
    secret = b"attacker-chosen-shared-secret-0123456789"
    token = jwt.encode(
        {"sub": USER_ID, "iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 60},
        secret, algorithm="HS256", headers={"kid": "kid-rsa"},
    )
    expect_auth_error(v.verify(token), "TOKEN_INVALID")


def test_algorithm_not_in_allow_list_rejected() -> None:
    v = make_verifier(FakeJWKS(RSA), algorithms=("ES256",))
    expect_auth_error(v.verify(RSA.token()), "TOKEN_INVALID")


def test_key_type_must_match_algorithm() -> None:
    # Header says RS256 but kid resolves to an EC key.
    v = make_verifier(FakeJWKS(EC))
    forged = jwt.encode(
        {"sub": USER_ID, "iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 60},
        RSA.private, algorithm="RS256", headers={"kid": "kid-ec"},
    )
    expect_auth_error(v.verify(forged), "TOKEN_INVALID")


def test_missing_kid_rejected() -> None:
    v = make_verifier(FakeJWKS(EC))
    token = jwt.encode(
        {"sub": USER_ID, "iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 60},
        EC.private, algorithm="ES256",
    )
    expect_auth_error(v.verify(token), "TOKEN_INVALID")


def test_malformed_and_oversized_tokens_rejected() -> None:
    v = make_verifier(FakeJWKS(EC))
    expect_auth_error(v.verify("not.a.jwt"), "TOKEN_MALFORMED")
    expect_auth_error(v.verify(""), "TOKEN_MALFORMED")
    expect_auth_error(v.verify("a" * 9000), "TOKEN_MALFORMED")


def test_unknown_kid_rejected_after_single_refresh() -> None:
    src = FakeJWKS(EC)
    v = make_verifier(src)
    stranger = TestKey("kid-unknown", "EC")
    expect_auth_error(v.verify(stranger.token()), "TOKEN_INVALID")
    assert src.calls == 1


def test_key_rotation_refreshes_once_cooldown_elapsed() -> None:
    clock = FakeClock()
    src = FakeJWKS(EC)
    v = make_verifier(src, clock)
    assert run(v.verify(EC.token()))
    new_key = TestKey("kid-new", "EC")
    src.keys.append(new_key)
    clock.now += 31  # past cooldown, cache still fresh
    assert run(v.verify(new_key.token()))
    assert src.calls == 2


def test_unknown_kid_flood_does_not_refetch_within_cooldown() -> None:
    clock = FakeClock()
    src = FakeJWKS(EC)
    v = make_verifier(src, clock)
    run(v.verify(EC.token()))
    for i in range(5):
        expect_auth_error(v.verify(TestKey(f"junk-{i}", "EC").token()), "TOKEN_INVALID")
    assert src.calls == 1


def test_known_kid_served_from_cache() -> None:
    src = FakeJWKS(EC)
    v = make_verifier(src)
    for _ in range(3):
        run(v.verify(EC.token()))
    assert src.calls == 1


def test_jwks_outage_fails_closed_with_503() -> None:
    src = FakeJWKS(EC)
    src.fail = True
    v = make_verifier(src)
    expect_auth_error(v.verify(EC.token()), "JWKS_UNAVAILABLE", status=503)


def test_jwks_outage_not_hammered_within_cooldown() -> None:
    src = FakeJWKS(EC)
    src.fail = True
    v = make_verifier(src)
    for _ in range(4):
        expect_auth_error(v.verify(EC.token()), "JWKS_UNAVAILABLE", status=503)
    assert src.calls == 1


def test_recovers_after_outage() -> None:
    clock = FakeClock()
    src = FakeJWKS(EC)
    src.fail = True
    v = make_verifier(src, clock)
    expect_auth_error(v.verify(EC.token()), "JWKS_UNAVAILABLE", status=503)
    src.fail = False
    clock.now += 31
    assert run(v.verify(EC.token()))


def test_stale_cache_refetched_after_ttl() -> None:
    clock = FakeClock()
    src = FakeJWKS(EC)
    v = make_verifier(src, clock)
    run(v.verify(EC.token()))
    clock.now += 601
    run(v.verify(EC.token()))
    assert src.calls == 2


def test_jwks_with_private_material_or_no_usable_keys_is_rejected() -> None:
    leaky = TestKey("kid-leaky", "EC")
    leaky.jwk["d"] = "AAAA"
    src = FakeJWKS(leaky)
    v = make_verifier(src)
    expect_auth_error(v.verify(leaky.token()), "JWKS_INVALID", status=503)


def test_future_nbf_rejected() -> None:
    v = make_verifier(FakeJWKS(EC))
    expect_auth_error(v.verify(EC.token(nbf=int(time.time()) + 3600)), "TOKEN_INVALID")


def test_past_nbf_accepted() -> None:
    v = make_verifier(FakeJWKS(EC))
    assert run(v.verify(EC.token(nbf=int(time.time()) - 60)))


def test_audience_list_containing_expected_audience_accepted() -> None:
    v = make_verifier(FakeJWKS(EC))
    assert run(v.verify(EC.token(aud=[AUDIENCE, "other"])))


def test_ec_jwk_with_leading_zero_coordinate_is_accepted() -> None:
    """Regression for the earlier intermittent failure: keys whose x or y starts with 0x00."""
    for _ in range(20000):
        k = TestKey("kid-zero", "EC")
        nums = k.private.public_key().public_numbers()
        if nums.x.bit_length() <= 248 or nums.y.bit_length() <= 248:  # leading zero byte
            break
    else:
        raise AssertionError("could not generate a leading-zero key (statistically unexpected)")
    assert len(base64.urlsafe_b64decode(k.jwk["x"] + "==")) == 32
    assert len(base64.urlsafe_b64decode(k.jwk["y"] + "==")) == 32
    assert run(make_verifier(FakeJWKS(k)).verify(k.token()))


def test_helper_jwk_is_always_fixed_length() -> None:
    for _ in range(300):
        jwk = ec_p256_public_jwk(ec.generate_private_key(ec.SECP256R1()).public_key())
        assert len(base64.urlsafe_b64decode(jwk["x"] + "==")) == 32
        assert len(base64.urlsafe_b64decode(jwk["y"] + "==")) == 32


def test_concurrent_cold_requests_trigger_a_single_fetch() -> None:
    src = FakeJWKS(EC)
    src.delay = 0.01
    v = make_verifier(src)

    async def burst() -> list[object]:
        return await asyncio.gather(*[v.verify(EC.token()) for _ in range(10)])

    assert len(run(burst())) == 10
    assert src.calls == 1


def test_failed_refresh_keeps_cached_keys_serving_known_kids() -> None:
    clock = FakeClock()
    src = FakeJWKS(EC)
    v = make_verifier(src, clock)
    run(v.verify(EC.token()))
    clock.now += 31
    src.fail = True
    expect_auth_error(v.verify(TestKey("kid-other", "EC").token()), "JWKS_UNAVAILABLE", status=503)
    assert run(v.verify(EC.token()))  # known kid still verifies from the fresh cache
    assert src.calls == 2


def test_invalid_refresh_document_does_not_wipe_cache() -> None:
    clock = FakeClock()
    src = FakeJWKS(EC)
    v = make_verifier(src, clock)
    run(v.verify(EC.token()))
    clock.now += 31
    src.keys = []  # server now returns {"keys": []}
    expect_auth_error(v.verify(TestKey("kid-other", "EC").token()), "JWKS_INVALID", status=503)
    assert run(v.verify(EC.token()))


def test_removed_key_stays_trusted_until_ttl_then_fails_closed() -> None:
    """Documents the accepted 24h-cache trade-off (SECURITY_ARCHITECTURE s1)."""
    clock = FakeClock()
    src = FakeJWKS(EC)
    v = make_verifier(src, clock)
    run(v.verify(EC.token()))
    src.keys = [TestKey("kid-replacement", "EC")]  # EC "revoked" upstream
    clock.now += 300
    assert run(v.verify(EC.token()))  # still served from cache
    clock.now += 600  # beyond the 600s TTL used in tests
    expect_auth_error(v.verify(EC.token()), "TOKEN_INVALID")  # refreshed: kid gone


def test_user_metadata_email_verified_not_trusted() -> None:
    """Proof that user_metadata.email_verified is NEVER trusted as proof of email verification."""
    v = make_verifier(FakeJWKS(EC))
    token = EC.token(user_metadata={"email_verified": True})
    user = run(v.verify(token))
    assert user.email_verified is False, "user_metadata MUST NOT be used to establish email_verified!"


def test_root_email_verified_claim_trusted() -> None:
    """Proof that signed top-level root claim email_verified=True is trusted."""
    v = make_verifier(FakeJWKS(EC))
    token = EC.token(email_verified=True)
    user = run(v.verify(token))
    assert user.email_verified is True


def test_root_email_confirmed_at_claim_trusted() -> None:
    """Proof that signed top-level root claim email_confirmed_at is trusted."""
    v = make_verifier(FakeJWKS(EC))
    token = EC.token(email_confirmed_at="2026-11-06T12:00:00Z")
    user = run(v.verify(token))
    assert user.email_verified is True


def test_missing_verification_claims_defaults_to_false() -> None:
    """Proof that tokens without root verification signals fail closed with email_verified=False."""
    v = make_verifier(FakeJWKS(EC))
    token = EC.token()
    user = run(v.verify(token))
    assert user.email_verified is False
