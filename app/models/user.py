from datetime import datetime

import bcrypt
from sqlalchemy.orm import validates

from app import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120), nullable=True)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    @validates("email")
    def _validate_email(self, key, value):
        if not value or "@" not in value:
            raise ValueError("email must contain '@'")
        return value.strip().lower()

    def set_password(self, plaintext):
        self.password_hash = bcrypt.hashpw(
            plaintext.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    def check_password(self, plaintext):
        if not self.password_hash:
            return False
        return bcrypt.checkpw(
            plaintext.encode("utf-8"), self.password_hash.encode("utf-8")
        )
