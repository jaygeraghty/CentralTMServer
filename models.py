from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Date, Text, 
    DateTime, ForeignKey, Index, 
    CheckConstraint, CHAR
)
from sqlalchemy.orm import relationship, declarative_mixin
from app import db

# Base class for SQLAlchemy models
Base = db.Model

@declarative_mixin
class ScheduleMixin:
    """Mixin with common fields for all schedule tables."""
    id = Column(Integer, primary_key=True)
    uid = Column(Text, nullable=False)
    stp_indicator = Column(CHAR(1), nullable=False)  # 'P', 'N', 'O', 'C'
    transaction_type = Column(CHAR(1), nullable=False)  # 'N', 'D', 'R'
    runs_from = Column(Date, nullable=False)
    runs_to = Column(Date, nullable=False)
    days_run = Column(CHAR(7), nullable=False)  # Binary format (Mon-Sun)
    train_status = Column(CHAR(1), nullable=False)
    train_category = Column(Text, nullable=False)
    train_identity = Column(Text, nullable=False)  # Headcode
    service_code = Column(Text, nullable=False)
    power_type = Column(Text, nullable=False)
    speed = Column(Integer, nullable=True)
    operating_chars = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

@declarative_mixin
class LocationMixin:
    """Mixin with common fields for all schedule location tables."""
    id = Column(Integer, primary_key=True)
    sequence = Column(Integer, nullable=False)
    location_type = Column(CHAR(2), nullable=False)  # 'LO', 'LI', 'LT'
    tiploc = Column(Text, nullable=False)
    arr = Column(Text, nullable=True)
    dep = Column(Text, nullable=True)
    pass_time = Column(Text, nullable=True)
    public_arr = Column(Text, nullable=True)
    public_dep = Column(Text, nullable=True)
    platform = Column(Text, nullable=True)
    line = Column(Text, nullable=True)
    path = Column(Text, nullable=True)
    activity = Column(Text, nullable=True)
    engineering_allowance = Column(Text, nullable=True)
    pathing_allowance = Column(Text, nullable=True)
    performance_allowance = Column(Text, nullable=True)

@declarative_mixin
class AssociationMixin:
    """Mixin with common fields for all association tables."""
    id = Column(Integer, primary_key=True)
    main_uid = Column(Text, nullable=False)
    assoc_uid = Column(Text, nullable=False)
    category = Column(CHAR(2), nullable=False)  # 'JJ', 'VV', 'NP'
    date_from = Column(Date, nullable=False)
    date_to = Column(Date, nullable=False)
    days_run = Column(CHAR(7), nullable=False)  # Binary format (Mon-Sun)
    location = Column(Text, nullable=False)  # TIPLOC
    base_suffix = Column(CHAR(1), nullable=True)
    assoc_suffix = Column(CHAR(1), nullable=True)
    date_indicator = Column(CHAR(1), nullable=True)  # 'S', 'N', 'P'
    stp_indicator = Column(CHAR(1), nullable=False)  # 'P', 'N', 'O', 'C'
    transaction_type = Column(CHAR(1), nullable=False)  # 'N', 'D', 'R'
    created_at = Column(DateTime, default=datetime.now, nullable=False)

class ParsedFile(Base):
    """
    Stores information about processed CIF files.
    """
    __tablename__ = "parsed_files"
    
    id = Column(Integer, primary_key=True)
    file_ref = Column(String(7), unique=True, nullable=False)
    extract_type = Column(CHAR(1), nullable=False)  # 'F' for full, 'U' for update
    processed_at = Column(DateTime, default=datetime.now, nullable=False)
    filename = Column(String(255), nullable=False)

# Legacy schedule tables (kept for backward compatibility)
class BasicSchedule(Base):
    """
    Stores basic schedule information from BS records.
    This is the original table schema, maintained for backward compatibility.
    New code should use the STP-specific tables instead.
    """
    __tablename__ = "basic_schedules"
    
    id = Column(Integer, primary_key=True)
    uid = Column(Text, nullable=False)
    stp_indicator = Column(CHAR(1), nullable=False)  # 'P', 'N', 'O', 'C'
    transaction_type = Column(CHAR(1), nullable=False)  # 'N', 'D', 'R'
    runs_from = Column(Date, nullable=False)
    runs_to = Column(Date, nullable=False)
    days_run = Column(CHAR(7), nullable=False)  # Binary format (Mon-Sun)
    train_status = Column(CHAR(1), nullable=False)
    train_category = Column(Text, nullable=False)
    train_identity = Column(Text, nullable=False)  # Headcode
    service_code = Column(Text, nullable=False)
    power_type = Column(Text, nullable=False)
    speed = Column(Integer, nullable=True)
    operating_chars = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    
    # Relationships
    locations = relationship("ScheduleLocation", back_populates="schedule", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index("ix_basic_schedules_uid", uid),
        Index("ix_basic_schedules_runs_from", runs_from),
        Index("ix_basic_schedules_runs_to", runs_to),
    )

class ScheduleLocation(Base):
    """
    Stores schedule location information from LO, LI, LT records.
    This is the original table schema, maintained for backward compatibility.
    New code should use the STP-specific tables instead.
    """
    __tablename__ = "schedule_locations"
    
    id = Column(Integer, primary_key=True)
    schedule_id = Column(Integer, ForeignKey("basic_schedules.id", ondelete="CASCADE"), nullable=False)
    sequence = Column(Integer, nullable=False)
    location_type = Column(CHAR(2), nullable=False)  # 'LO', 'LI', 'LT'
    tiploc = Column(Text, nullable=False)
    arr = Column(Text, nullable=True)
    dep = Column(Text, nullable=True)
    pass_time = Column(Text, nullable=True)
    public_arr = Column(Text, nullable=True)
    public_dep = Column(Text, nullable=True)
    platform = Column(Text, nullable=True)
    line = Column(Text, nullable=True)
    path = Column(Text, nullable=True)
    activity = Column(Text, nullable=True)
    engineering_allowance = Column(Text, nullable=True)
    pathing_allowance = Column(Text, nullable=True)
    performance_allowance = Column(Text, nullable=True)
    
    # Relationships
    schedule = relationship("BasicSchedule", back_populates="locations")
    
    # Indexes
    __table_args__ = (
        Index("ix_schedule_locations_schedule_id", schedule_id),
        Index("ix_schedule_locations_tiploc", tiploc),
    )

# STP-specific schedule tables
class ScheduleLTP(Base, ScheduleMixin):
    """Permanent schedules that are part of the Long-Term Plan."""
    __tablename__ = "schedules_ltp"
    
    # Relationships
    locations = relationship("ScheduleLocationLTP", back_populates="schedule", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index("ix_schedules_ltp_uid", "uid"),
        Index("ix_schedules_ltp_runs_from", "runs_from"),
        Index("ix_schedules_ltp_runs_to", "runs_to"),
    )

class ScheduleSTPNew(Base, ScheduleMixin):
    """New STP schedules with no matching LTP record."""
    __tablename__ = "schedules_stp_new"
    
    # Relationships
    locations = relationship("ScheduleLocationSTPNew", back_populates="schedule", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index("ix_schedules_stp_new_uid", "uid"),
        Index("ix_schedules_stp_new_runs_from", "runs_from"),
        Index("ix_schedules_stp_new_runs_to", "runs_to"),
    )

class ScheduleSTPOverlay(Base, ScheduleMixin):
    """STP schedules that temporarily replace or modify an LTP record."""
    __tablename__ = "schedules_stp_overlay"
    
    # Relationships
    locations = relationship("ScheduleLocationSTPOverlay", back_populates="schedule", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index("ix_schedules_stp_overlay_uid", "uid"),
        Index("ix_schedules_stp_overlay_runs_from", "runs_from"),
        Index("ix_schedules_stp_overlay_runs_to", "runs_to"),
    )

class ScheduleSTPCancellation(Base, ScheduleMixin):
    """STP cancellations that temporarily remove a permanent record."""
    __tablename__ = "schedules_stp_cancellation"
    
    # Relationships
    locations = relationship("ScheduleLocationSTPCancellation", back_populates="schedule", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index("ix_schedules_stp_cancellation_uid", "uid"),
        Index("ix_schedules_stp_cancellation_runs_from", "runs_from"),
        Index("ix_schedules_stp_cancellation_runs_to", "runs_to"),
    )

# STP-specific location tables
class ScheduleLocationLTP(Base, LocationMixin):
    """Location records for permanent schedules that are part of the Long-Term Plan."""
    __tablename__ = "schedule_locations_ltp"
    
    schedule_id = Column(Integer, ForeignKey("schedules_ltp.id", ondelete="CASCADE"), nullable=False)
    
    # Relationships
    schedule = relationship("ScheduleLTP", back_populates="locations")
    
    # Indexes
    __table_args__ = (
        Index("ix_schedule_locations_ltp_schedule_id", "schedule_id"),
        Index("ix_schedule_locations_ltp_tiploc", "tiploc"),
    )

class ScheduleLocationSTPNew(Base, LocationMixin):
    """Location records for new STP schedules with no matching LTP record."""
    __tablename__ = "schedule_locations_stp_new"
    
    schedule_id = Column(Integer, ForeignKey("schedules_stp_new.id", ondelete="CASCADE"), nullable=False)
    
    # Relationships
    schedule = relationship("ScheduleSTPNew", back_populates="locations")
    
    # Indexes
    __table_args__ = (
        Index("ix_schedule_locations_stp_new_schedule_id", "schedule_id"),
        Index("ix_schedule_locations_stp_new_tiploc", "tiploc"),
    )

class ScheduleLocationSTPOverlay(Base, LocationMixin):
    """Location records for STP schedules that temporarily replace or modify an LTP record."""
    __tablename__ = "schedule_locations_stp_overlay"
    
    schedule_id = Column(Integer, ForeignKey("schedules_stp_overlay.id", ondelete="CASCADE"), nullable=False)
    
    # Relationships
    schedule = relationship("ScheduleSTPOverlay", back_populates="locations")
    
    # Indexes
    __table_args__ = (
        Index("ix_schedule_locations_stp_overlay_schedule_id", "schedule_id"),
        Index("ix_schedule_locations_stp_overlay_tiploc", "tiploc"),
    )

class ScheduleLocationSTPCancellation(Base, LocationMixin):
    """Location records for STP cancellations that temporarily remove a permanent record."""
    __tablename__ = "schedule_locations_stp_cancellation"
    
    schedule_id = Column(Integer, ForeignKey("schedules_stp_cancellation.id", ondelete="CASCADE"), nullable=False)
    
    # Relationships
    schedule = relationship("ScheduleSTPCancellation", back_populates="locations")
    
    # Indexes
    __table_args__ = (
        Index("ix_schedule_locations_stp_cancellation_schedule_id", "schedule_id"),
        Index("ix_schedule_locations_stp_cancellation_tiploc", "tiploc"),
    )

# Legacy association table (kept for backward compatibility)
class Association(Base):
    """
    Stores association information from AA records.
    This is the original table schema, maintained for backward compatibility.
    New code should use the STP-specific tables instead.
    """
    __tablename__ = "associations"
    
    id = Column(Integer, primary_key=True)
    main_uid = Column(Text, nullable=False)
    assoc_uid = Column(Text, nullable=False)
    category = Column(CHAR(2), nullable=False)  # 'JJ', 'VV', 'NP'
    date_from = Column(Date, nullable=False)
    date_to = Column(Date, nullable=False)
    days_run = Column(CHAR(7), nullable=False)  # Binary format (Mon-Sun)
    location = Column(Text, nullable=False)  # TIPLOC
    base_suffix = Column(CHAR(1), nullable=True)
    assoc_suffix = Column(CHAR(1), nullable=True)
    date_indicator = Column(CHAR(1), nullable=True)  # 'S', 'N', 'P'
    stp_indicator = Column(CHAR(1), nullable=False)  # 'P', 'N', 'O', 'C'
    transaction_type = Column(CHAR(1), nullable=False)  # 'N', 'D', 'R'
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    
    # Indexes
    __table_args__ = (
        Index("ix_associations_main_uid", main_uid),
        Index("ix_associations_assoc_uid", assoc_uid),
        Index("ix_associations_location", location),
        Index("ix_associations_date_from", date_from),
        Index("ix_associations_date_to", date_to),
    )

# STP-specific association tables
class AssociationLTP(Base, AssociationMixin):
    """Permanent associations that are part of the Long-Term Plan."""
    __tablename__ = "associations_ltp"
    
    # Indexes
    __table_args__ = (
        Index("ix_associations_ltp_main_uid", "main_uid"),
        Index("ix_associations_ltp_assoc_uid", "assoc_uid"),
        Index("ix_associations_ltp_location", "location"),
        Index("ix_associations_ltp_date_from", "date_from"),
        Index("ix_associations_ltp_date_to", "date_to"),
    )

class AssociationSTPNew(Base, AssociationMixin):
    """New STP associations with no matching LTP record."""
    __tablename__ = "associations_stp_new"
    
    # Indexes
    __table_args__ = (
        Index("ix_associations_stp_new_main_uid", "main_uid"),
        Index("ix_associations_stp_new_assoc_uid", "assoc_uid"),
        Index("ix_associations_stp_new_location", "location"),
        Index("ix_associations_stp_new_date_from", "date_from"),
        Index("ix_associations_stp_new_date_to", "date_to"),
    )

class AssociationSTPOverlay(Base, AssociationMixin):
    """STP associations that temporarily replace or modify an LTP record."""
    __tablename__ = "associations_stp_overlay"
    
    # Indexes
    __table_args__ = (
        Index("ix_associations_stp_overlay_main_uid", "main_uid"),
        Index("ix_associations_stp_overlay_assoc_uid", "assoc_uid"),
        Index("ix_associations_stp_overlay_location", "location"),
        Index("ix_associations_stp_overlay_date_from", "date_from"),
        Index("ix_associations_stp_overlay_date_to", "date_to"),
    )

class AssociationSTPCancellation(Base, AssociationMixin):
    """STP cancellations that temporarily remove a permanent association record."""
    __tablename__ = "associations_stp_cancellation"
    
    # Indexes
    __table_args__ = (
        Index("ix_associations_stp_cancellation_main_uid", "main_uid"),
        Index("ix_associations_stp_cancellation_assoc_uid", "assoc_uid"),
        Index("ix_associations_stp_cancellation_location", "location"),
        Index("ix_associations_stp_cancellation_date_from", "date_from"),
        Index("ix_associations_stp_cancellation_date_to", "date_to"),
    )