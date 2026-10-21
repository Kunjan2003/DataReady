from app.db.session import SessionLocal
from app.services.processing import process_file

def process_file_job(file_id: int):
    db = SessionLocal()
    try:
        process_file(db, file_id)
    finally:
        db.close()
