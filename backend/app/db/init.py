from app.db.session import Base, engine
from app.models import models  # noqa: F401

def init_db():
    Base.metadata.create_all(bind=engine)
