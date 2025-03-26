from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.core.db import Base

class AppResource(Base):
    __tablename__ = "app_resource"

    app_resource_id = Column(
         Integer, primary_key=True, index=True, autoincrement=True
    )
    organization_id = Column(String, nullable=False, default="global") 
    file_name = Column(String, nullable=False)
    file_url = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    last_updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())