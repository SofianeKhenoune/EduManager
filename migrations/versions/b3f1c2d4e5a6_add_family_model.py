"""Add Family model, migrate Student and Payment

Revision ID: b3f1c2d4e5a6
Revises: 1afe981df5c7
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa

revision = "b3f1c2d4e5a6"
down_revision = "23abb42ee202"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # ── 1. Créer la table families ────────────────────────────
    op.create_table(
        "families",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("school_year", sa.Text(), nullable=False, server_default="2025-2026"),
        sa.Column("tarif_type", sa.Text(), nullable=False, server_default="normal"),
        sa.Column("father_first_name", sa.Text(), nullable=True),
        sa.Column("father_last_name", sa.Text(), nullable=True),
        sa.Column("father_phone", sa.Text(), nullable=True),
        sa.Column("father_email", sa.Text(), nullable=True),
        sa.Column("mother_first_name", sa.Text(), nullable=True),
        sa.Column("mother_last_name", sa.Text(), nullable=True),
        sa.Column("mother_phone", sa.Text(), nullable=True),
        sa.Column("mother_email", sa.Text(), nullable=True),
        sa.Column("address_number", sa.Integer(), nullable=True),
        sa.Column("street", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("zip_code", sa.Text(), nullable=True),
        sa.CheckConstraint("tarif_type IN ('normal', 'special')", name="check_family_tarif_type"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── 2. Nouvelles colonnes sur students ────────────────────
    op.add_column("students", sa.Column("family_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_students_family_id", "students", "families", ["family_id"], ["id"])
    op.add_column("students", sa.Column("gender", sa.Text(), nullable=True))
    op.add_column(
        "students",
        sa.Column("is_reinscription", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_check_constraint("check_student_gender", "students", "gender IN ('M', 'F')")

    # ── 3. Data migration : une famille par élève existant ────
    students = conn.execute(sa.text(
        "SELECT id, father_first_name, father_last_name, father_phone, father_email, "
        "mother_first_name, mother_last_name, mother_phone, mother_email, "
        "address_number, street, city, zip_code FROM students"
    )).fetchall()

    for s in students:
        result = conn.execute(sa.text(
            "INSERT INTO families "
            "(school_year, tarif_type, father_first_name, father_last_name, father_phone, father_email, "
            "mother_first_name, mother_last_name, mother_phone, mother_email, "
            "address_number, street, city, zip_code) "
            "VALUES ('2025-2026', 'normal', :ffn, :fln, :fp, :fe, :mfn, :mln, :mp, :me, :an, :st, :ci, :zp) "
            "RETURNING id"
        ), {
            "ffn": s.father_first_name, "fln": s.father_last_name,
            "fp": s.father_phone, "fe": s.father_email,
            "mfn": s.mother_first_name, "mln": s.mother_last_name,
            "mp": s.mother_phone, "me": s.mother_email,
            "an": s.address_number, "st": s.street,
            "ci": s.city, "zp": s.zip_code,
        })
        family_id = result.fetchone()[0]
        conn.execute(
            sa.text("UPDATE students SET family_id = :fid WHERE id = :sid"),
            {"fid": family_id, "sid": s.id},
        )

    # ── 4. Migrer payments : student_id → family_id ───────────
    op.add_column("payments", sa.Column("family_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_payments_family_id", "payments", "families", ["family_id"], ["id"])

    conn.execute(sa.text(
        "UPDATE payments p SET family_id = s.family_id "
        "FROM students s WHERE p.student_id = s.id"
    ))

    op.drop_constraint("payments_student_id_fkey", "payments", type_="foreignkey")
    op.drop_column("payments", "student_id")

    # ── 5. Supprimer les anciennes colonnes de students ───────
    op.drop_constraint("check_address_number", "students", type_="check")
    for col in (
        "father_first_name", "father_last_name", "father_phone", "father_email",
        "mother_first_name", "mother_last_name", "mother_phone", "mother_email",
        "address_number", "street", "city", "zip_code",
    ):
        op.drop_column("students", col)


def downgrade():
    raise NotImplementedError("Downgrade not supported for this migration.")
