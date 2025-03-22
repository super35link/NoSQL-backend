"""initial

Revision ID: c70b6d7261ba
Revises: 
Create Date: 2025-01-27 12:57:01.362851+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c70b6d7261ba'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('hashtags',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tag', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('usage_count', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_hashtags_id'), 'hashtags', ['id'], unique=False)
    op.create_index(op.f('ix_hashtags_tag'), 'hashtags', ['tag'], unique=True)
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('hashed_password', sa.String(length=1024), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_superuser', sa.Boolean(), nullable=False),
    sa.Column('is_verified', sa.Boolean(), nullable=False),
    sa.Column('username', sa.String(length=30), nullable=False),
    sa.Column('first_name', sa.String(length=50), nullable=True),
    sa.Column('last_name', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_table('follows',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('follower_id', sa.Integer(), nullable=False),
    sa.Column('following_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['follower_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['following_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('follower_id', 'following_id', name='unique_follows')
    )
    op.create_table('profiles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('avatar_url', sa.String(), nullable=True),
    sa.Column('banner_url', sa.String(), nullable=True),
    sa.Column('bio', sa.String(length=500), nullable=True),
    sa.Column('location', sa.String(), nullable=True),
    sa.Column('website', sa.String(), nullable=True),
    sa.Column('is_private', sa.Boolean(), nullable=True),
    sa.Column('show_activity_status', sa.Boolean(), nullable=True),
    sa.Column('profile_views', sa.Integer(), nullable=True),
    sa.Column('last_active', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('posts_count', sa.Integer(), nullable=True),
    sa.Column('saved_posts_count', sa.Integer(), nullable=True),
    sa.Column('media_count', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.create_table('settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('language', sa.String(), nullable=True),
    sa.Column('theme', sa.String(), nullable=True),
    sa.Column('timezone', sa.String(), nullable=True),
    sa.Column('autoplay_videos', sa.Boolean(), nullable=True),
    sa.Column('who_can_see_posts', sa.String(), nullable=True),
    sa.Column('who_can_reply', sa.String(), nullable=True),
    sa.Column('allow_messages', sa.Boolean(), nullable=True),
    sa.Column('show_read_receipts', sa.Boolean(), nullable=True),
    sa.Column('notify_new_followers', sa.Boolean(), nullable=True),
    sa.Column('notify_likes', sa.Boolean(), nullable=True),
    sa.Column('notify_reposts', sa.Boolean(), nullable=True),
    sa.Column('notify_mentions', sa.Boolean(), nullable=True),
    sa.Column('notify_replies', sa.Boolean(), nullable=True),
    sa.Column('push_enabled', sa.Boolean(), nullable=True),
    sa.Column('email_enabled', sa.Boolean(), nullable=True),
    sa.Column('sensitive_content', sa.Boolean(), nullable=True),
    sa.Column('quality_filter', sa.Boolean(), nullable=True),
    sa.Column('muted_words', sa.JSON(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.create_table('threads',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('creator_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('status', sa.Enum('active', 'complete', name='threadstatus'), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['creator_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_threads_id'), 'threads', ['id'], unique=False)
    op.create_table('blocked_users',
    sa.Column('blocker_id', sa.Integer(), nullable=False),
    sa.Column('blocked_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['blocked_id'], ['profiles.id'], ),
    sa.ForeignKeyConstraint(['blocker_id'], ['profiles.id'], ),
    sa.PrimaryKeyConstraint('blocker_id', 'blocked_id')
    )
    op.create_table('posts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('content', sa.String(length=500), nullable=False),
    sa.Column('author_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('thread_id', sa.Integer(), nullable=True),
    sa.Column('position_in_thread', sa.Integer(), nullable=True),
    sa.Column('reply_to_id', sa.Integer(), nullable=True),
    sa.Column('content_vector', sa.ARRAY(sa.Float()), nullable=True),
    sa.Column('like_count', sa.Integer(), nullable=True),
    sa.Column('view_count', sa.Integer(), nullable=True),
    sa.Column('repost_count', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reply_to_id'], ['posts.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['thread_id'], ['threads.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_posts_id'), 'posts', ['id'], unique=False)
    op.create_table('profile_media',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('profile_id', sa.Integer(), nullable=True),
    sa.Column('media_type', sa.String(), nullable=True),
    sa.Column('media_url', sa.String(), nullable=True),
    sa.Column('uploaded_at', sa.DateTime(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['profile_id'], ['profiles.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('profile_views',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('profile_id', sa.Integer(), nullable=True),
    sa.Column('viewer_id', sa.Integer(), nullable=True),
    sa.Column('viewed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['profile_id'], ['profiles.id'], ),
    sa.ForeignKeyConstraint(['viewer_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('post_hashtags',
    sa.Column('post_id', sa.Integer(), nullable=True),
    sa.Column('hashtag_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['hashtag_id'], ['hashtags.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['post_id'], ['posts.id'], ondelete='CASCADE')
    )
    op.create_table('post_mentions',
    sa.Column('post_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['post_id'], ['posts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('post_mentions')
    op.drop_table('post_hashtags')
    op.drop_table('profile_views')
    op.drop_table('profile_media')
    op.drop_index(op.f('ix_posts_id'), table_name='posts')
    op.drop_table('posts')
    op.drop_table('blocked_users')
    op.drop_index(op.f('ix_threads_id'), table_name='threads')
    op.drop_table('threads')
    op.drop_table('settings')
    op.drop_table('profiles')
    op.drop_table('follows')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_hashtags_tag'), table_name='hashtags')
    op.drop_index(op.f('ix_hashtags_id'), table_name='hashtags')
    op.drop_table('hashtags')
    # ### end Alembic commands ###
