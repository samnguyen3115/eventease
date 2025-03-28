from datetime import datetime, timezone
from typing import Optional
from app import db, login
import sqlalchemy as sqla
import sqlalchemy.orm as sqlo
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from sqlalchemy.dialects.postgresql import ARRAY


@login.user_loader
def load_user(id):
    return db.session.get(User, int(id))


# Association Table for Tags and Posts
postTags = db.Table(
    'postTags',
    db.metadata,
    sqla.Column('post_id', sqla.Integer, sqla.ForeignKey('post.id', ondelete='CASCADE'), primary_key=True),
    sqla.Column('tag_id', sqla.Integer, sqla.ForeignKey('tag.id', ondelete='CASCADE'), primary_key=True)
)


# User Model
class User(UserMixin, db.Model):
    id: sqlo.Mapped[int] = sqlo.mapped_column(primary_key=True)
    username: sqlo.Mapped[str] = sqlo.mapped_column(sqla.String(64), unique=True, nullable=False)
    email: sqlo.Mapped[str] = sqlo.mapped_column(sqla.String(120), unique=True, nullable=False)
    password_hash: sqlo.Mapped[Optional[str]] = sqlo.mapped_column(sqla.String(256))
    posts: sqlo.WriteOnlyMapped[list["Post"]] = sqlo.relationship("Post", back_populates='writer', cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return self.password_hash is not None and check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User id={self.id} username={self.username}>"
    
    def get_user_posts(self):
        return db.session.execute(self.posts.select().order_by(Post.timestamp.desc())).scalars().all()



# Tag Model
class Tag(db.Model):
    id: sqlo.Mapped[int] = sqlo.mapped_column(primary_key=True)
    name: sqlo.Mapped[str] = sqlo.mapped_column(sqla.String(50), unique=True, nullable=False)
    category: sqlo.Mapped[str] = sqlo.mapped_column(sqla.String(20), nullable=False)  # e.g., "color" or "building"

    def __repr__(self):
        return f"<Tag id={self.id} name={self.name} category={self.category}>"


# Post Model
class Post(db.Model):
    id: sqlo.Mapped[int] = sqlo.mapped_column(primary_key=True)
    userid: sqlo.Mapped[int] = sqlo.mapped_column(sqla.ForeignKey(User.id, ondelete="CASCADE"), index=True)
    title: sqlo.Mapped[str] = sqlo.mapped_column(sqla.String(150), nullable=False)
    description: sqlo.Mapped[str] = sqlo.mapped_column(sqla.String(1500), nullable=False)
    timestamp: sqlo.Mapped[Optional[datetime]] = sqlo.mapped_column(default=lambda: datetime.now(timezone.utc))

    # Relationships for color and building tags
    color_tag_id: sqlo.Mapped[int] = sqlo.mapped_column(sqla.ForeignKey('tag.id'), nullable=False)
    color_tag: sqlo.Mapped["Tag"] = sqlo.relationship(
        "Tag",
        foreign_keys=[color_tag_id],
        primaryjoin="and_(Post.color_tag_id == Tag.id, Tag.category == 'color')",
        lazy="joined"
    )

    building_tag_id: sqlo.Mapped[int] = sqlo.mapped_column(sqla.ForeignKey('tag.id'), nullable=False)
    building_tag: sqlo.Mapped["Tag"] = sqlo.relationship(
        "Tag",
        foreign_keys=[building_tag_id],
        primaryjoin="and_(Post.building_tag_id == Tag.id, Tag.category == 'building')",
        lazy="joined"
    )

    writer: sqlo.Mapped["User"] = sqlo.relationship("User", back_populates="posts")
    image = db.relationship('ImageStore', backref='post', uselist=False)

    def __repr__(self):
        return f"<Post id={self.id} title={self.title}>"


# Image Store Model
class ImageStore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id', ondelete='CASCADE'), nullable=False)
    image_data = db.Column(db.LargeBinary, nullable=False)
    image_type = db.Column(db.String(50), nullable=True)

class Building(db.Model):
    building_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    count = db.Column(db.Integer)
    title = db.Column(ARRAY(db.String(200)))
    body = db.Column(ARRAY(db.String(200)))
    theme_image_link = db.Column(db.String(50))
    image_link = db.Column(ARRAY(db.String(50)))
    
    def get_name(self):
        return self.name
    def get_count(self):
        return self.count
    def get_place(self):
        return self.title
    def get_body(self):
        return self.body
    def get_image(self):
        return self.image_link
    def get_theme(self):
        return self.theme_image_link