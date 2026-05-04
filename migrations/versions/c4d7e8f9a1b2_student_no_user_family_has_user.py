"""student_no_user_family_has_user

Revision ID: c4d7e8f9a1b2
Revises: b3f1c2d4e5a6
Create Date: 2026-05-01

- students : supprime user_id, ajoute first_name + last_name
- families : ajoute user_id (compte parent, optionnel)
- Nettoie les Users qui étaient liés à des étudiants
"""

from alembic import op
import sqlalchemy as sa

revision = "c4d7e8f9a1b2"
down_revision = "b3f1c2d4e5a6"
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. Ajouter first_name / last_name à students (nullable d'abord) ──
    op.add_column("students", sa.Column("first_name", sa.Text(), nullable=True))
    op.add_column("students", sa.Column("last_name", sa.Text(), nullable=True))

    # ── 2. Migrer les données depuis users ──
    op.execute("""
        UPDATE students s
        SET first_name = u.first_name,
            last_name  = u.last_name
        FROM users u
        WHERE u.id = s.user_id
    """)

    # ── 3. Rendre NOT NULL maintenant que les données sont là ──
    op.alter_column("students", "first_name", nullable=False, server_default=sa.text("''"))
    op.alter_column("students", "last_name",  nullable=False, server_default=sa.text("''"))

    # ── 4. Ajouter user_id à families (compte parent optionnel) ──
    op.add_column("families", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_families_user_id", "families", "users", ["user_id"], ["id"]
    )
    op.create_unique_constraint("uq_families_user_id", "families", ["user_id"])

    # ── 5. Supprimer les Users ayant le rôle 'student' ──
    #    (d'abord on récupère les ids pour ne pas casser des FK)
    op.execute("""
        DELETE FROM users
        WHERE id IN (
            SELECT user_id FROM students WHERE user_id IS NOT NULL
        )
        AND role_id = (SELECT id FROM roles WHERE name = 'student')
    """)

    # ── 6. Supprimer user_id de students ──
    op.drop_constraint("students_user_id_fkey", "students", type_="foreignkey")
    op.drop_constraint("students_user_id_key",  "students", type_="unique")
    op.drop_column("students", "user_id")


def downgrade():
    # Ré-ajouter user_id (nullable — on ne peut pas recréer les Users)
    op.add_column("students", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "students_user_id_fkey", "students", "users", ["user_id"], ["id"]
    )
    op.create_unique_constraint("students_user_id_key", "students", ["user_id"])

    # Supprimer user_id de families
    op.drop_constraint("uq_families_user_id", "families", type_="unique")
    op.drop_constraint("fk_families_user_id",  "families", type_="foreignkey")
    op.drop_column("families", "user_id")

    # Supprimer first_name / last_name de students
    op.drop_column("students", "last_name")
    op.drop_column("students", "first_name")
