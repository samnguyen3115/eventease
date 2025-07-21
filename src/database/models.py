from datetime import datetime, timedelta
from typing import Optional
from src import db, login
import sqlalchemy as sqla
import sqlalchemy.orm as sqlo
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import secrets
from flask import current_app

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
event_participants = db.Table(
    'event_participants',
    db.metadata,
    sqla.Column('user_id', sqla.Integer, sqla.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True),
    sqla.Column('event_id', sqla.Integer, sqla.ForeignKey('event.id', ondelete='CASCADE'), primary_key=True)
)
friendships = db.Table(
    'friendships',
    db.metadata,
    sqla.Column('user_id', sqla.Integer, sqla.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True),
    sqla.Column('friend_id', sqla.Integer, sqla.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True)
)
# User Model
class User(UserMixin, db.Model):
    id: sqlo.Mapped[int] = sqlo.mapped_column(primary_key=True)
    username: sqlo.Mapped[str] = sqlo.mapped_column(sqla.String(64), unique=True, nullable=False)
    email: sqlo.Mapped[str] = sqlo.mapped_column(sqla.String(120), unique=True, nullable=False)
    password_hash: sqlo.Mapped[Optional[str]] = sqlo.mapped_column(sqla.String(256))
    language: sqlo.Mapped[str] = sqlo.mapped_column(sqla.String(10), default="en-EN", nullable=True)  # Default language set to English
    profile_picture = sqlo.mapped_column(sqla.String(120), nullable=True)
    
    # Email verification fields
    email_verified: sqlo.Mapped[bool] = sqlo.mapped_column(sqla.Boolean, default=False)
    email_verification_token: sqlo.Mapped[Optional[str]] = sqlo.mapped_column(sqla.String(256), nullable=True)
    email_verification_token_expiry: sqlo.Mapped[Optional[datetime]] = sqlo.mapped_column(sqla.DateTime, nullable=True)
    
    # Password reset fields
    reset_token: sqlo.Mapped[Optional[str]] = sqlo.mapped_column(sqla.String(256), nullable=True)
    reset_token_expiry: sqlo.Mapped[Optional[datetime]] = sqlo.mapped_column(sqla.DateTime, nullable=True)
    
    # Account security fields
    last_login: sqlo.Mapped[Optional[datetime]] = sqlo.mapped_column(sqla.DateTime, nullable=True)
    failed_login_attempts: sqlo.Mapped[int] = sqlo.mapped_column(sqla.Integer, default=0)
    account_locked_until: sqlo.Mapped[Optional[datetime]] = sqlo.mapped_column(sqla.DateTime, nullable=True)
    
    events: sqlo.WriteOnlyMapped[list["Event"]] = sqlo.relationship("Event", back_populates="user", cascade="all, delete-orphan")
    tasks: sqlo.Mapped[list["Task"]] = sqlo.relationship(
        "Task",
        secondary=task_assignments,
        back_populates="assigned_users"
    )
    friends: sqlo.Mapped[list["User"]] = sqlo.relationship(
        "User",
        secondary=friendships,
        primaryjoin=id == friendships.c.user_id,
        secondaryjoin=id == friendships.c.friend_id,
        backref="friend_of",
        lazy="dynamic"
    )
    def add_friend(self, friend):
        """Add a friend to the user's friends list."""
        if not self.is_friend(friend):
            self.friends.append(friend)

    def is_friend(self, friend):
        """Check if a user is already a friend."""
        return self.friends.filter(friendships.c.friend_id == friend.id).count() > 0

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return self.password_hash is not None and check_password_hash(self.password_hash, password)

    def generate_reset_token(self):
        """Generate a secure token for password reset"""
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
        return self.reset_token

    def verify_reset_token(self, token):
        """Verify reset token and check if it's still valid"""
        if not self.reset_token or not self.reset_token_expiry:
            return False
        if datetime.utcnow() > self.reset_token_expiry:
            return False
        return self.reset_token == token

    def clear_reset_token(self):
        """Clear the reset token after use"""
        self.reset_token = None
        self.reset_token_expiry = None

    def generate_email_verification_token(self):
        """Generate a secure token for email verification"""
        self.email_verification_token = secrets.token_urlsafe(32)
        self.email_verification_token_expiry = datetime.utcnow() + timedelta(hours=24)  # 24 hours for email verification
        return self.email_verification_token

    def verify_email_verification_token(self, token):
        """Verify email verification token and check if it's still valid"""
        if not self.email_verification_token or not self.email_verification_token_expiry:
            return False
        if datetime.utcnow() > self.email_verification_token_expiry:
            return False
        return self.email_verification_token == token

    def clear_email_verification_token(self):
        """Clear the email verification token after use"""
        self.email_verification_token = None
        self.email_verification_token_expiry = None

    def verify_email(self):
        """Mark email as verified"""
        self.email_verified = True
        self.clear_email_verification_token()

    def is_email_verified(self):
        """Check if email is verified"""
        return self.email_verified

    def is_account_locked(self):
        """Check if account is currently locked"""
        if self.account_locked_until:
            return datetime.utcnow() < self.account_locked_until
        return False

    def increment_failed_login(self):
        """Increment failed login attempts and lock account if necessary"""
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:  # Lock after 5 failed attempts
            self.account_locked_until = datetime.utcnow() + timedelta(minutes=15)

    def reset_failed_login_attempts(self):
        """Reset failed login attempts after successful login"""
        self.failed_login_attempts = 0
        self.account_locked_until = None
        self.last_login = datetime.utcnow()

    def __repr__(self):
        return f"<User id={self.id} username={self.username}>"
    
    participating_events: sqlo.Mapped[list["Event"]] = sqlo.relationship(
    "Event",
    secondary=event_participants,
    back_populates="participants"
    )


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
    strict_mode = db.Column(db.Boolean, default=False,nullable = True)  # New field for strict mode

    def __repr__(self):
        return f"<Event id={self.id} name={self.name}>"
    participants: sqlo.Mapped[list["User"]] = sqlo.relationship(
    "User",
    secondary=event_participants,
    back_populates="participating_events"
    )


# Task Model
class Task(db.Model):
    id: sqlo.Mapped[int] = sqlo.mapped_column(primary_key=True)
    description: sqlo.Mapped[str] = sqlo.mapped_column(sqla.String(255), nullable=False)
    note: sqlo.Mapped[Optional[str]] = sqlo.mapped_column(sqla.String(500), nullable=True)  # Optional note field
    completed: sqlo.Mapped[bool] = sqlo.mapped_column(sqla.Boolean, default=False)
    priority: sqlo.Mapped[int] = sqlo.mapped_column(sqla.Integer, nullable=False)  # Task priority (e.g., 1=Low, 2=Medium, 3=High)
    due_date: sqlo.Mapped[Optional[datetime]] = sqlo.mapped_column(sqla.DateTime, nullable=True)  # Optional due date
    event_id: sqlo.Mapped[int] = sqlo.mapped_column(sqla.Integer, sqla.ForeignKey('event.id', ondelete="CASCADE"))
    event: sqlo.Mapped["Event"] = sqlo.relationship("Event", back_populates="tasks")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    item = db.Column(db.String(100), nullable=True)
    image_link = db.Column(db.String(200), nullable=True)

    # Add passive_deletes=True to handle delete operations without loading the relationship
    assigned_users: sqlo.Mapped[list["User"]] = sqlo.relationship(
        "User",
        secondary=task_assignments,
        back_populates="tasks",
        passive_deletes=True
    )
    

    def __repr__(self):
        return f"<Task id={self.id} description={self.description[:20]} priority={self.priority} due_date={self.due_date} completed={self.completed}>"


