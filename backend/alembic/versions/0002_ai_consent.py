"""Record whether AI assisted processing was enabled per uploaded file."""
from alembic import op
import sqlalchemy as sa

revision = "0002_ai_consent"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("uploaded_files", sa.Column("allow_ai", sa.Boolean(), nullable=False, server_default=sa.false()))

def downgrade():
    op.drop_column("uploaded_files", "allow_ai")
