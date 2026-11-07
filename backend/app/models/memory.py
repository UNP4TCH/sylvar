"""Living Brand Memory and Snapshot models (Domain D)."""
import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.document import RuleCategory


class MemoryVersionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


# Association table between memory versions and rule revisions
brand_memory_version_rules = Table(
    "brand_memory_version_rules",
    Base.metadata,
    Column(
        "memory_version_id",
        PG_UUID(as_uuid=True),
        ForeignKey("brand_memory_versions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "rule_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("brand_rule_revisions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class BrandMemoryVersion(Base):
    __tablename__ = "brand_memory_versions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "client_id", "version_tag", name="uq_memory_versions_tag"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("client_brands.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    version_tag: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        SAEnum(MemoryVersionStatus, name="memory_version_status", native_enum=True, create_type=False, values_callable=lambda x: [e.value for e in x]),
        default=MemoryVersionStatus.DRAFT.value,
        nullable=False,
    )
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    rule_revisions: Mapped[list["BrandRuleRevision"]] = relationship(
        "BrandRuleRevision",
        secondary=brand_memory_version_rules,
        back_populates="memory_versions",
    )
    snapshots: Mapped[list["BrandMemorySnapshot"]] = relationship(
        "BrandMemorySnapshot", back_populates="memory_version", cascade="all, delete-orphan"
    )


class BrandRule(Base):
    __tablename__ = "brand_rules"
    __table_args__ = (
        UniqueConstraint("workspace_id", "client_id", "rule_code", name="uq_brand_rules_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("client_brands.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_code: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(
        SAEnum(RuleCategory, name="rule_category", native_enum=True, create_type=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
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

    revisions: Mapped[list["BrandRuleRevision"]] = relationship(
        "BrandRuleRevision", back_populates="rule", cascade="all, delete-orphan"
    )


class BrandRuleRevision(Base):
    """Immutable rule revision (RULES Law 5)."""

    __tablename__ = "brand_rule_revisions"
    __table_args__ = (
        UniqueConstraint("rule_id", "revision_number", name="uq_rule_revision"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("brand_rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    rule: Mapped[BrandRule] = relationship("BrandRule", back_populates="revisions")
    memory_versions: Mapped[list[BrandMemoryVersion]] = relationship(
        BrandMemoryVersion,
        secondary=brand_memory_version_rules,
        back_populates="rule_revisions",
    )


class BrandMemorySnapshot(Base):
    """Frozen materialized rulebook with verifiable SHA-256 hash (ADR-006)."""

    __tablename__ = "brand_memory_snapshots"
    __table_args__ = (
        Index("idx_brand_memory_snapshots_hash", "snapshot_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("client_brands.id", ondelete="CASCADE"),
        nullable=False,
    )
    memory_version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("brand_memory_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    snapshot_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    memory_version: Mapped[BrandMemoryVersion] = relationship(
        "BrandMemoryVersion", back_populates="snapshots"
    )
