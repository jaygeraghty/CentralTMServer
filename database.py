
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Get database URL from environment variables
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/railway")

# Create SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Check connection before using
    pool_recycle=300,    # Recycle connections every 5 minutes
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base for declarative models
Base = declarative_base()

class DB:
    def __init__(self):
        self.session = SessionLocal()

    def close(self):
        self.session.close()

# Function to get database session
def get_db():
    """
    Get a database session wrapper.
    
    Returns:
        DB: Database wrapper with session attribute
    """
    return DB()
