"""Authoritative server-side email verification against Supabase GoTrue Admin API.

Used to verify user identities when the client-presented JWT lacks root-level
email_verified or email_confirmed_at claims.

Security guarantees:
1. Directly queries GoTrue auth.users using backend-only service-role credentials.
2. Checks authoritative email_confirmed_at timestamp.
3. Asserts exact case-insensitive email match against expected identity.
4. Fails closed on any error, timeout, missing claim, or mismatch.
5. NEVER trusts client-submitted user_metadata.
"""
import logging
import uuid

import httpx

from app.core.config import get_settings

logger = logging.getLogger("sylvar.security.gotrue")


async def verify_identity_with_gotrue(user_id: uuid.UUID, expected_email: str) -> bool:
    """Verify an identity's email confirmation status directly against Supabase GoTrue Admin API."""
    settings = get_settings()

    if not settings.supabase_url or not settings.supabase_service_role_key:
        logger.debug(
            "Supabase service-role credentials not configured; cannot verify user %s with GoTrue",
            user_id,
        )
        return False

    admin_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{user_id}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(admin_url, headers=headers)
            if resp.status_code != 200:
                logger.warning(
                    "GoTrue admin lookup for user %s returned status %s",
                    user_id,
                    resp.status_code,
                )
                return False

            data = resp.json()
            remote_email = str(data.get("email") or "").strip().lower()
            norm_expected = expected_email.strip().lower()

            if remote_email != norm_expected:
                logger.warning(
                    "Email mismatch for user %s: GoTrue has '%s', expected '%s'",
                    user_id,
                    remote_email,
                    norm_expected,
                )
                return False

            # Check authoritative confirmation timestamp in GoTrue auth.users
            confirmed_at = data.get("email_confirmed_at") or data.get("confirmed_at")
            if not confirmed_at:
                logger.info(
                    "User %s (%s) is registered in GoTrue but email is not confirmed (email_confirmed_at is null)",
                    user_id,
                    remote_email,
                )
                return False

            logger.info("Authoritative email confirmation established for %s via GoTrue", remote_email)
            return True

    except Exception as exc:
        logger.error("Failed to verify user %s with GoTrue: %s", user_id, exc)
        return False  # Fail closed

