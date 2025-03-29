from datetime import datetime
from typing import Optional
from app import db, login
import sqlalchemy as sqla
import sqlalchemy.orm as sqlo
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

# @login.user_loader
@login.user_loader
def load_user(id):
    return db.session.get(User, int(id))

# Association Table for Task Assignments (Many-to-Many: Users <-> Tasks)
task_assignments = db.Table(
    'task_assignments',
    db.metadata,
    sqla.Column('user_id', sqla.Integer, sqla.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True),
    sqla.Column('task_id', sqla.Integer, sqla.ForeignKey('task.id', ondelete='CASCADE'), primary_key=True)
)

# User Model
class User(UserMixin, db.Model):
    id: sqlo.Mapped[int] = sqlo.mapped_column(primary_key=True)
    username: sqlo.Mapped[str] = sqlo.mapped_column(sqla.String(64), unique=True, nullable=False)
    email: sqlo.Mapped[str] = sqlo.mapped_column(sqla.String(120), unique=True, nullable=False)
    password_hash: sqlo.Mapped[Optional[str]] = sqlo.mapped_column(sqla.String(256))
    events: sqlo.WriteOnlyMapped[list["Event"]] = sqlo.relationship("Event", back_populates="user", cascade="all, delete-orphan")
    tasks: sqlo.WriteOnlyMapped[list["Task"]] = sqlo.relationship("Task", secondary=task_assignments, back_populates="assigned_users")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return self.password_hash is not None and check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User id={self.id} username={self.username}>"

# Event Model
from sqlalchemy.orm import relationship

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete="CASCADE"))
    user = db.relationship("User", back_populates="events")
    tasks = db.relationship("Task", back_populates="event", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Event id={self.id} name={self.name}>"

# Task Model
class Task(db.Model):
    id: sqlo.Mapped[int] = sqlo.mapped_column(primary_key=True)
    description: sqlo.Mapped[str] = sqlo.mapped_column(sqla.String(255), nullable=False)
    completed: sqlo.Mapped[bool] = sqlo.mapped_column(sqla.Boolean, default=False)
    priority: sqlo.Mapped[int] = sqlo.mapped_column(sqla.Integer, nullable=False)  # Task priority (e.g., 1=Low, 2=Medium, 3=High)
    due_date: sqlo.Mapped[Optional[datetime]] = sqlo.mapped_column(sqla.DateTime, nullable=True)  # Optional due date
    event_id: sqlo.Mapped[int] = sqlo.mapped_column(sqla.Integer, sqla.ForeignKey('event.id', ondelete="CASCADE"))
    event: sqlo.Mapped["Event"] = sqlo.relationship("Event", back_populates="tasks")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    assigned_users: sqlo.WriteOnlyMapped[list["User"]] = sqlo.relationship("User", secondary=task_assignments, back_populates="tasks")

    def __repr__(self):
        return f"<Task id={self.id} description={self.description[:20]} priority={self.priority} due_date={self.due_date} completed={self.completed}>"

