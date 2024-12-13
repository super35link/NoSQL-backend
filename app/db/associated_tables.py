from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Table
from app.db.base import Base


# Association tables
post_hashtags = Table(
    'post_hashtags', Base.metadata,
    Column('post_id', Integer, ForeignKey('posts.id', ondelete='CASCADE')),
    Column('hashtag_id', Integer, ForeignKey('hashtags.id', ondelete='CASCADE'))
)

post_mentions = Table(
    'post_mentions', Base.metadata,
    Column('post_id', Integer, ForeignKey('posts.id', ondelete='CASCADE')),
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'))
)