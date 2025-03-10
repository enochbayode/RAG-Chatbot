# app/core/db.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

# getting the Postgres database url from .env file
DATABASE_URL = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_PUBLIC_IP')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"


# DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in the environment variables")

# Create database engine with connection pooling
engine = None
try: 
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,        # Max number of database connections
        max_overflow=20,     # Allow extra connections beyond pool size
        echo=False           # Set to True for SQL query logging
    )
    print (engine)
    print("✅ Connected to the database successfully!")

except Exception as e:
    print(f"❌ Connection failed: {e}")

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for ORM models
Base = declarative_base()

# Dependency function to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
