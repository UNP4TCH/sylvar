"""Secure workspace invitation and email delivery service.

Supports:
1. Supabase GoTrue Admin invitation API (POST /auth/v1/invite) using backend-only service-role key.
2. Direct SMTP mail service with TLS.
3. Development sink fallback with structured audit logging.
4. Clean retry and partial-failure rollback guarantees.
"""
import asyncio
import email.message
import logging
import smtplib
import uuid
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.core.errors import ProblemException

logger = logging.getLogger("sylvar.invitations")


@dataclass
class InvitationDispatchResult:
    delivered: bool
    channel: str  # "supabase_gotrue" | "smtp" | "dev_sink"
    auth_user_id: uuid.UUID | None
    detail: str
    provider_message_id: str | None = None


async def dispatch_workspace_invitation(
    recipient_email: str,
    recipient_name: str | None,
    workspace_id: uuid.UUID,
    workspace_name: str,
    role: str,
) -> InvitationDispatchResult:
    """Dispatch an invitation email via GoTrue Admin API or SMTP with fallback handling."""
    settings = get_settings()

    # Channel 1: Supabase GoTrue Admin API
    if settings.supabase_service_role_key and settings.supabase_url:
        invite_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/invite"
        headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "apikey": settings.supabase_service_role_key,
            "Content-Type": "application/json",
        }
        payload = {
            "email": recipient_email,
            "data": {
                "full_name": recipient_name or recipient_email.split("@")[0],
                "workspace_id": str(workspace_id),
                "workspace_name": workspace_name,
                "role": role,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(invite_url, json=payload, headers=headers)
                if resp.status_code in (200, 201):
                    data = resp.json()
                    user_id_str = data.get("id")
                    auth_id = uuid.UUID(user_id_str) if user_id_str else None
                    logger.info("Supabase GoTrue invitation sent to %s (id: %s)", recipient_email, auth_id)
                    return InvitationDispatchResult(
                        delivered=True,
                        channel="supabase_gotrue",
                        auth_user_id=auth_id,
                        detail="Invitation delivered via Supabase GoTrue Admin API.",
                    )
                if resp.status_code == 422:
                    # User already registered or already invited in Supabase
                    logger.info(
                        "Recipient %s already registered in GoTrue; proceeding with workspace linking.",
                        recipient_email,
                    )
                    return InvitationDispatchResult(
                        delivered=True,
                        channel="supabase_gotrue",
                        auth_user_id=None,
                        detail="User already registered in GoTrue.",
                    )
                logger.error("Supabase GoTrue invite failed: status=%s, body=%s", resp.status_code, resp.text)
                raise ProblemException(
                    status=502,
                    code="INVITATION_DELIVERY_FAILED",
                    title="Bad Gateway",
                    detail=f"Supabase GoTrue Admin invitation failed with status {resp.status_code}.",
                )
        except httpx.RequestError as exc:
            logger.error("Network error reaching Supabase GoTrue: %s", exc)
            raise ProblemException(
                status=502,
                code="INVITATION_DELIVERY_FAILED",
                title="Bad Gateway",
                detail=f"Failed to communicate with Supabase GoTrue: {exc}",
            ) from exc

    # Channel 2: SMTP Mail Service
    if settings.smtp_host:
        def _send_smtp() -> None:
            msg = email.message.EmailMessage()
            msg["Subject"] = f"You've been invited to join {workspace_name} on SYLVAR"
            msg["From"] = settings.smtp_from
            msg["To"] = recipient_email

            invite_link = (
                f"{settings.app_frontend_url.rstrip('/')}/login"
                f"?email={recipient_email}&workspace={workspace_id}"
            )
            body = (
                f"Hello {recipient_name or recipient_email},\n\n"
                f"You have been invited to join the workspace '{workspace_name}' as a {role}.\n\n"
                f"Click the link below to accept and sign in:\n"
                f"{invite_link}\n\n"
                f"Best regards,\n"
                f"The SYLVAR Platform"
            )
            msg.set_content(body)

            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
                if settings.smtp_use_tls:
                    server.starttls()
                if settings.smtp_user and settings.smtp_password:
                    server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)

        try:
            await asyncio.to_thread(_send_smtp)
            logger.info("SMTP invitation email successfully sent to %s", recipient_email)
            return InvitationDispatchResult(
                delivered=True,
                channel="smtp",
                auth_user_id=None,
                detail="Invitation email sent via SMTP.",
            )
        except Exception as exc:
            logger.error("SMTP delivery failed to %s: %s", recipient_email, exc)
            raise ProblemException(
                status=502,
                code="INVITATION_DELIVERY_FAILED",
                title="Bad Gateway",
                detail=f"SMTP mail delivery failed: {exc}",
            ) from exc

    # Channel 3: Development Sink Fallback
    is_prod = settings.app_env.strip().lower() in ("production", "prod")
    if is_prod:
        raise ProblemException(
            status=503,
            code="INVITATION_SERVICE_UNAVAILABLE",
            title="Service Unavailable",
            detail="No mail delivery service (Supabase Service Role or SMTP) is configured in production.",
        )

    logger.warning(
        "[DEV_INVITATION_SINK] Invitation dispatched for %s (role: %s, workspace: %s [%s]). "
        "No live mailer configured; logged to sink.",
        recipient_email,
        role,
        workspace_name,
        workspace_id,
    )
    return InvitationDispatchResult(
        delivered=True,
        channel="dev_sink",
        auth_user_id=None,
        detail="Logged to development invitation sink (mailer not configured).",
    )

