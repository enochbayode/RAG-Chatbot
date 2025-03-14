# app/models/document.py
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from datetime import datetime
from app.core.db import Base


class Document(Base):
    __tablename__ = "chatbot_resource"  # chat resource is the table name

    chat_bot_resource_id = Column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    organization_id = Column(
        String, nullable=False
    )  # Organization ID for multi-tenancy
    file_name = Column(String, nullable=False)
    file_url = Column(String, nullable=False)  # Store Google Cloud Storage link
    created_at = Column(DateTime, default=func.now())  # use DB timestamp
    last_updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
