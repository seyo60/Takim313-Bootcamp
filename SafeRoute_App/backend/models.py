"""SQLAlchemy models kept in parity with the Alembic head."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    func,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base

from geoalchemy2 import Geography


Base = declarative_base()


class H3HeatmapModel(Base):
    __tablename__ = "h3_heatmap"
    __table_args__ = (
        UniqueConstraint(
            "h3_resolution",
            "h3_index",
            name="uq_h3_heatmap_resolution_index",
        ),
        CheckConstraint(
            "h3_resolution IN (9, 10)",
            name="chk_h3_heatmap_h3_resolution",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    h3_index = Column(String(15), index=True, nullable=False)
    h3_resolution = Column(SmallInteger, nullable=False, default=10, server_default="10", index=True)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    location = Column(Geography(geometry_type="POINT", srid=4326))
    risk_crime = Column(Float, default=0.0)
    risk_lighting = Column(Float, default=0.0)
    risk_live = Column(Float, default=0.0)
    total_risk = Column(Float, default=0.0)
    domestic = Column(Boolean, default=False)
    location_description = Column(String(255))
    date = Column(DateTime(timezone=True), index=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        index=True,
    )
    extra_features = Column(JSONB, nullable=True, default=dict)


class ReportEventModel(Base):
    __tablename__ = "report_events"
    __table_args__ = (
        CheckConstraint("h3_resolution IN (9, 10)", name="chk_report_events_h3_resolution"),
    )

    id = Column(Integer, primary_key=True, index=True)
    uuid_id = Column(String(36), unique=True, index=True, nullable=False)
    h3_index = Column(String(15), index=True, nullable=False)
    h3_resolution = Column(SmallInteger, nullable=False, default=9, server_default="9", index=True)
    normalized_category = Column(String(50), nullable=False, default="general_safety")
    priority = Column(String(20), nullable=False, default="normal")
    status = Column(String(20), nullable=False, default="pending", index=True)
    unique_reporter_count = Column(Integer, default=1)
    mean_similarity = Column(Float, default=1.0)
    mean_user_reliability = Column(Float, default=0.50)
    mean_model_confidence = Column(Float, default=0.50)
    validation_score = Column(Float, default=0.0)
    severity_weight = Column(Float, default=0.35)
    analysis_method = Column(String(50), default="deterministic_fallback")
    first_seen_at = Column(DateTime(timezone=True), index=True)
    last_seen_at = Column(DateTime(timezone=True), index=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), index=True, nullable=True)
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))


class UserProfileModel(Base):
    __tablename__ = "user_profiles"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'moderator', 'admin')", name="chk_user_profiles_role"),
    )

    user_id = Column(UUID(as_uuid=True), primary_key=True)
    display_name = Column(String(80), nullable=True)
    role = Column(String(20), nullable=False, default="user", server_default="user")
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    deletion_requested_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class ReportModel(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    uuid_id = Column(String(36), unique=True, index=True, nullable=False)
    tracking_token = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    description = Column(String(255), nullable=False)
    category = Column(String(50), default="general", nullable=False)
    priority = Column(String(20), default="normal", nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    # Legacy column retained for migration compatibility. New writes keep it NULL.
    ip_address = Column(String(45), nullable=True)
    location = Column(Geography(geometry_type="POINT", srid=4326))
    created_at = Column(DateTime(timezone=True), index=True)
    event_id = Column(
        Integer,
        ForeignKey("report_events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reporter_hash = Column(String(64), nullable=True, index=True)
    normalized_category = Column(String(50), nullable=True)
    severity_weight = Column(Float, nullable=True)
    model_confidence = Column(Float, nullable=True)
    analysis_method = Column(String(50), nullable=True)


class ETLRunModel(Base):
    __tablename__ = "etl_runs"

    id = Column(Integer, primary_key=True, index=True)
    etl_name = Column(String(50), unique=True, index=True, nullable=False)
    last_successful_run = Column(DateTime(timezone=True), nullable=False)
    records_processed = Column(Integer, default=0)
    status = Column(String(20), default="success", nullable=False)


class UserDeviceModel(Base):
    """Push token + son bilinen konum (1 km acil bildirim hedefleme)."""

    __tablename__ = "user_devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    expo_push_token = Column(String(255), unique=True, nullable=False, index=True)
    last_lat = Column(Float, nullable=True)
    last_lng = Column(Float, nullable=True)
    location = Column(Geography(geometry_type="POINT", srid=4326), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, index=True)


class EmergencyAlertModel(Base):
    """Acil ihbar için DeepSeek üretilmiş tanık/yayın bildirimleri."""

    __tablename__ = "emergency_alerts"
    __table_args__ = (
        CheckConstraint(
            "phase IN ('witness_request', 'broadcast')",
            name="chk_emergency_alerts_phase",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    uuid_id = Column(String(36), unique=True, index=True, nullable=False)
    event_id = Column(
        Integer,
        ForeignKey("report_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    report_uuid = Column(String(36), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    phase = Column(String(32), nullable=False, index=True)
    title = Column(String(120), nullable=False)
    body = Column(String(280), nullable=False)
    llm_method = Column(String(64), nullable=False, default="deterministic_fallback")
    confirm_count = Column(Integer, nullable=False, default=0)
    deny_count = Column(Integer, nullable=False, default=0)
    push_target_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)
    broadcast_sent_at = Column(DateTime(timezone=True), nullable=True)


class AlertConfirmationModel(Base):
    """Yakındaki kullanıcının 'gördüm / görmedim' yanıtı."""

    __tablename__ = "alert_confirmations"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "user_id",
            name="uq_alert_confirmations_event_user",
        ),
        CheckConstraint(
            "response IN ('confirm', 'deny', 'unsure')",
            name="chk_alert_confirmations_response",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(
        Integer,
        ForeignKey("report_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alert_id = Column(
        Integer,
        ForeignKey("emergency_alerts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    response = Column(String(16), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
