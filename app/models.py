from sqlalchemy import Column, String, Float
from .database import Base

class Loaner(Base):
    __tablename__ = "loaners"

    loaner_id = Column(String(50), primary_key=True)
    fullname = Column(String(255))
    mobile_no = Column(String(20))
    loaner_adhar = Column(String(20))
    total_amount = Column(Float)
    total_land = Column(String(50))
    descrition = Column(String(500))