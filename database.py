"""
Database models and setup using SQLAlchemy + SQLite.
"""

from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float,
    DateTime, Boolean, Text, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker, relationship

DATABASE_URL = "sqlite:///./fitzrovia.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class Building(Base):
    __tablename__ = "buildings"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    address = Column(String, nullable=False)
    url = Column(String, nullable=False)
    last_scraped_at = Column(DateTime, nullable=True)
    scrape_status = Column(String, default="pending")  # pending, success, failed
    scrape_error = Column(Text, nullable=True)

    units = relationship("UnitListing", back_populates="building", cascade="all, delete-orphan")


class UnitListing(Base):
    __tablename__ = "unit_listings"

    id = Column(Integer, primary_key=True, index=True)
    building_id = Column(Integer, ForeignKey("buildings.id"), nullable=False)

    # Core fields
    unit_number = Column(String, nullable=True)
    unit_type = Column(String, nullable=False)       # Bachelor, 1-Bed, 2-Bed, 3-Bed
    bedrooms = Column(Integer, nullable=True)         # 0=Bachelor, 1, 2, 3
    bathrooms = Column(Float, nullable=True)
    floor_plan_name = Column(String, nullable=True)

    # Pricing
    monthly_rent = Column(Float, nullable=True)
    rent_min = Column(Float, nullable=True)           # For floor plan ranges
    rent_max = Column(Float, nullable=True)

    # Space
    sq_ft = Column(Integer, nullable=True)
    sq_ft_min = Column(Integer, nullable=True)
    sq_ft_max = Column(Integer, nullable=True)
    floor = Column(Integer, nullable=True)

    # Availability
    available_date = Column(String, nullable=True)
    is_available = Column(Boolean, default=True)

    # Incentives
    incentives = Column(Text, nullable=True)          # Free-text description of offers

    # Meta
    scraped_at = Column(DateTime, default=datetime.utcnow)
    source_url = Column(String, nullable=True)        # Direct link to unit if available

    building = relationship("Building", back_populates="units")


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String, default="running")        # running, completed, failed
    buildings_scraped = Column(Integer, default=0)
    units_found = Column(Integer, default=0)
    errors = Column(Text, nullable=True)


def create_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Seed buildings on first run
BUILDINGS_CONFIG = [
    {
        "name": "Parker",
        "address": "200 Redpath Avenue, Toronto, ON",
        "url": "https://www.parkerlife.ca",
    },
    {
        "name": "Story of Midtown",
        "address": "75 Broadway Avenue, Toronto, ON",
        "url": "https://www.mystorymidtown.com",
    },
    {
        "name": "The Selby",
        "address": "25 Selby Street, Toronto, ON",
        "url": "https://triconliving.com/apartment/the-selby/",
    },
    {
        "name": "eCentral",
        "address": "15 Roehampton Avenue, Toronto, ON",
        "url": "https://www.ecentralliving.com",
    },
    {
        "name": "The Montgomery",
        "address": "2388 Yonge Street, Toronto, ON",
        "url": "https://www.themontgomery.ca",
    },
    {
        "name": "The Whitney",
        "address": "71 Redpath Avenue, Toronto, ON",
        "url": "https://www.thewhitneyonredpath.com",
    },
    {
        "name": "The Hampton",
        "address": "101 Roehampton Avenue, Toronto, ON",
        "url": "https://thehampton.ca",
    },
    {
        "name": "E18HTEEN",
        "address": "18 Erskine Avenue, Toronto, ON",
        "url": "https://www.myrental.ca/apartments-for-rent/18-erskine-ave",
    },
    {
        "name": "Corner on Broadway",
        "address": "223 Redpath Avenue, Toronto, ON",
        "url": "https://thecornerrentals.com",
    },
    {
        "name": "Akoya Living",
        "address": "55 Broadway Avenue, Toronto, ON",
        "url": "https://www.akoyaliving.ca",
    },
]


def seed_buildings(db):
    """Insert buildings if they don't exist yet."""
    for config in BUILDINGS_CONFIG:
        existing = db.query(Building).filter(Building.name == config["name"]).first()
        if not existing:
            db.add(Building(**config))
    db.commit()
