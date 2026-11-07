"""Client brand management and independent client assignment domain models (Domain B)."""
import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ClientRole(str, enum.Enum):
    """Client-level assigned roles."""

    BRAND_MANAGER = "BRAND_MANAGER"
    CONTENT_CREATOR = "CONTENT_CREATOR"


class ClientMembershipStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class ClientBrand(Base):
    __tablename__ = "client_brands"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_client_brands_workspace_id"),
        UniqueConstraint("workspace_id", "code", name="uq_client_brands_workspace_code"),
        Index("idx_client_brands_workspace", "workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agency_workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_memory_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    workspace: Mapped["AgencyWorkspace"] = relationship("AgencyWorkspace", back_populates="client_brands")  # type: ignore[name-defined] # noqa: F821
    memberships: Mapped[list["ClientMembership"]] = relationship(
        "ClientMembership", back_populates="client_brand", cascade="all, delete-orphan"
    )


class ClientMembership(Base):
    """Independent client brand assignment (ADR-003).

    Workspace membership does NOT ambiently grant client access.
    """

    __tablename__ = "client_memberships"
    __table_args__ = (
        UniqueConstraint("client_id", "user_id", name="uq_client_memberships_client_user"),
        Index("idx_client_memberships_lookup", "workspace_id", "client_id", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("client_brands.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    client_role: Mapped[str] = mapped_column(
        SAEnum(ClientRole, name="client_role", native_enum=True, create_type=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        SAEnum(ClientMembershipStatus, name="client_membership_status", native_enum=True, create_type=False, values_callable=lambda x: [e.value for e in x]),
        default=ClientMembershipStatus.ACTIVE.value,
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    client_brand: Mapped[ClientBrand] = relationship("ClientBrand", back_populates="memberships")
    user: Mapped["User"] = relationship("User", back_populates="client_memberships")  # type: ignore[name-defined] # noqa: F821
