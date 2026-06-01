"""Tests for sqlguard.migration module."""

import pytest
from sqlguard.schema import Schema, Table, Column, ForeignKey, Index
from sqlguard.diff import SchemaDiffer, ChangeType
from sqlguard.migration import MigrationGenerator, Migration, MigrationStep


class TestMigrationStep:
    """Tests for MigrationStep."""

    def test_to_sql(self):
        step = MigrationStep(
            sql="ALTER TABLE users ADD COLUMN bio TEXT;",
            change_type=ChangeType.COLUMN_ADDED,
            table="users",
            column="bio",
        )
        assert step.to_sql() == "ALTER TABLE users ADD COLUMN bio TEXT;"

    def test_to_sql_with_comment(self):
        step = MigrationStep(
            sql="ALTER TABLE users ADD COLUMN bio TEXT;",
            change_type=ChangeType.COLUMN_ADDED,
            table="users",
            column="bio",
            comment="Add bio column",
        )
        sql = step.to_sql()
        assert "-- Add bio column" in sql
        assert "ALTER TABLE" in sql

    def test_to_rollback_sql(self):
        step = MigrationStep(
            sql="ALTER TABLE users ADD COLUMN bio TEXT;",
            change_type=ChangeType.COLUMN_ADDED,
            table="users",
            column="bio",
            rollback_sql="ALTER TABLE users DROP COLUMN bio;",
        )
        rollback = step.to_rollback_sql()
        assert "DROP COLUMN bio" in rollback

    def test_to_rollback_sql_no_rollback(self):
        step = MigrationStep(
            sql="DROP TABLE users;",
            change_type=ChangeType.TABLE_REMOVED,
            table="users",
            reversible=False,
        )
        rollback = step.to_rollback_sql()
        assert "No automatic rollback" in rollback


class TestMigration:
    """Tests for Migration."""

    def test_empty_migration(self):
        migration = Migration(name="empty")
        assert migration.up_sql == "-- No migration steps\n"
        assert migration.down_sql == "-- No migration steps\n"

    def test_add_step(self):
        migration = Migration(name="test")
        step = MigrationStep(
            sql="ALTER TABLE users ADD COLUMN name VARCHAR(255);",
            change_type=ChangeType.COLUMN_ADDED,
            table="users",
            column="name",
        )
        migration.add_step(step)
        assert len(migration.steps) == 1

    def test_up_sql(self):
        migration = Migration(name="test")
        migration.add_step(MigrationStep(
            sql="ALTER TABLE users ADD COLUMN bio TEXT;",
            change_type=ChangeType.COLUMN_ADDED,
            table="users",
            column="bio",
            comment="Add bio column",
        ))
        migration.add_step(MigrationStep(
            sql="ALTER TABLE posts ADD COLUMN published BOOLEAN DEFAULT false;",
            change_type=ChangeType.COLUMN_ADDED,
            table="posts",
            column="published",
        ))
        sql = migration.up_sql
        assert "Migration: test" in sql
        assert "ALTER TABLE users" in sql
        assert "ALTER TABLE posts" in sql

    def test_down_sql_reversed(self):
        migration = Migration(name="test")
        step1 = MigrationStep(
            sql="ALTER TABLE users ADD COLUMN bio TEXT;",
            change_type=ChangeType.COLUMN_ADDED,
            table="users",
            rollback_sql="ALTER TABLE users DROP COLUMN bio;",
        )
        step2 = MigrationStep(
            sql="ALTER TABLE posts ADD COLUMN published BOOLEAN;",
            change_type=ChangeType.COLUMN_ADDED,
            table="posts",
            rollback_sql="ALTER TABLE posts DROP COLUMN published;",
        )
        migration.add_step(step1)
        migration.add_step(step2)

        down = migration.down_sql
        # Rollback should be in reverse order
        assert down.index("posts") < down.index("users")

    def test_has_breaking_steps(self):
        migration = Migration(name="test")
        migration.add_step(MigrationStep(
            sql="ALTER TABLE users ADD COLUMN bio TEXT;",
            change_type=ChangeType.COLUMN_ADDED,
            table="users",
        ))
        assert not migration.has_breaking_steps

        migration.add_step(MigrationStep(
            sql="ALTER TABLE users DROP COLUMN age;",
            change_type=ChangeType.COLUMN_REMOVED,
            table="users",
        ))
        assert migration.has_breaking_steps

    def test_summary(self):
        migration = Migration(name="test")
        migration.add_step(MigrationStep(
            sql="ALTER TABLE users ADD COLUMN bio TEXT;",
            change_type=ChangeType.COLUMN_ADDED,
            table="users",
            column="bio",
        ))
        summary = migration.summary()
        assert "Migration: test" in summary
        assert "Steps: 1" in summary


class TestMigrationGenerator:
    """Tests for migration generation from schema diffs."""

    def test_add_table(self):
        old = Schema("v1", [Table("users", [Column("id", "integer", primary_key=True)])])
        new = Schema("v2", [
            Table("users", [Column("id", "integer", primary_key=True)]),
            Table("posts", [
                Column("id", "integer", primary_key=True),
                Column("title", "varchar", nullable=False),
                Column("user_id", "integer", references="users.id"),
            ]),
        ])

        differ = SchemaDiffer()
        diff = differ.diff(old, new)
        generator = MigrationGenerator(dialect="postgresql")
        migration = generator.generate(diff, old_schema=old, new_schema=new)

        assert len(migration.steps) >= 1
        assert any("CREATE TABLE posts" in s.sql for s in migration.steps)

    def test_drop_table(self):
        old = Schema("v1", [
            Table("users", [Column("id", "integer", primary_key=True)]),
            Table("posts", [Column("id", "integer", primary_key=True)]),
        ])
        new = Schema("v2", [Table("users", [Column("id", "integer", primary_key=True)])])

        differ = SchemaDiffer()
        diff = differ.diff(old, new)
        generator = MigrationGenerator(dialect="postgresql")
        migration = generator.generate(diff, old_schema=old, new_schema=new)

        assert any("DROP TABLE posts" in s.sql for s in migration.steps)

    def test_add_column(self):
        old = Schema("v1", [Table("users", [
            Column("id", "integer", primary_key=True),
        ])])
        new = Schema("v2", [Table("users", [
            Column("id", "integer", primary_key=True),
            Column("email", "varchar", nullable=False, unique=True),
        ])])

        differ = SchemaDiffer()
        diff = differ.diff(old, new)
        generator = MigrationGenerator(dialect="postgresql")
        migration = generator.generate(diff, old_schema=old, new_schema=new)

        assert any("ADD COLUMN email" in s.sql for s in migration.steps)

    def test_drop_column(self):
        old = Schema("v1", [Table("users", [
            Column("id", "integer", primary_key=True),
            Column("age", "integer"),
        ])])
        new = Schema("v2", [Table("users", [
            Column("id", "integer", primary_key=True),
        ])])

        differ = SchemaDiffer()
        diff = differ.diff(old, new)
        generator = MigrationGenerator(dialect="postgresql")
        migration = generator.generate(diff, old_schema=old, new_schema=new)

        assert any("DROP COLUMN age" in s.sql for s in migration.steps)

    def test_alter_column_type(self):
        old = Schema("v1", [Table("users", [
            Column("id", "integer", primary_key=True),
            Column("age", "smallint"),
        ])])
        new = Schema("v2", [Table("users", [
            Column("id", "integer", primary_key=True),
            Column("age", "integer"),
        ])])

        differ = SchemaDiffer()
        diff = differ.diff(old, new)
        generator = MigrationGenerator(dialect="postgresql")
        migration = generator.generate(diff, old_schema=old, new_schema=new)

        type_changes = [s for s in migration.steps if s.change_type == ChangeType.COLUMN_TYPE_CHANGED]
        assert len(type_changes) >= 1

    def test_alter_nullability(self):
        old = Schema("v1", [Table("users", [
            Column("id", "integer", primary_key=True),
            Column("name", "varchar", nullable=True),
        ])])
        new = Schema("v2", [Table("users", [
            Column("id", "integer", primary_key=True),
            Column("name", "varchar", nullable=False),
        ])])

        differ = SchemaDiffer()
        diff = differ.diff(old, new)
        generator = MigrationGenerator(dialect="postgresql")
        migration = generator.generate(diff, old_schema=old, new_schema=new)

        null_changes = [s for s in migration.steps if s.change_type == ChangeType.COLUMN_NULLABILITY_CHANGED]
        assert len(null_changes) >= 1
        assert any("SET NOT NULL" in s.sql for s in null_changes)

    def test_mysql_dialect(self):
        old = Schema("v1", [Table("users", [Column("id", "integer", primary_key=True)])])
        new = Schema("v2", [Table("users", [
            Column("id", "integer", primary_key=True),
            Column("name", "varchar"),
        ])])

        differ = SchemaDiffer()
        diff = differ.diff(old, new)
        generator = MigrationGenerator(dialect="mysql")
        migration = generator.generate(diff, old_schema=old, new_schema=new)

        assert migration.dialect == "mysql"

    def test_sqlite_dialect(self):
        old = Schema("v1", [Table("users", [Column("id", "integer", primary_key=True)])])
        new = Schema("v2", [Table("users", [
            Column("id", "integer", primary_key=True),
            Column("name", "varchar"),
        ])])

        differ = SchemaDiffer()
        diff = differ.diff(old, new)
        generator = MigrationGenerator(dialect="sqlite")
        migration = generator.generate(diff, old_schema=old, new_schema=new)

        assert migration.dialect == "sqlite"
        # SQLite should use ADD COLUMN
        assert any("ADD COLUMN" in s.sql for s in migration.steps)

    def test_migration_ordering(self):
        """Verify that migration steps are ordered correctly."""
        old = Schema("v1", [
            Table("users", [
                Column("id", "integer", primary_key=True),
                Column("email", "varchar"),
                Column("age", "integer"),
            ]),
        ])
        new = Schema("v2", [
            Table("users", [
                Column("id", "integer", primary_key=True),
                Column("email", "varchar"),
                Column("bio", "text"),  # Added
            ]),
        ])

        differ = SchemaDiffer()
        diff = differ.diff(old, new)
        generator = MigrationGenerator(dialect="postgresql")
        migration = generator.generate(diff, old_schema=old, new_schema=new)

        # Column drops should come before column adds
        drop_step = None
        add_step = None
        for i, step in enumerate(migration.steps):
            if step.change_type == ChangeType.COLUMN_REMOVED:
                drop_step = i
            if step.change_type == ChangeType.COLUMN_ADDED:
                add_step = i

        if drop_step is not None and add_step is not None:
            assert drop_step < add_step

    def test_empty_diff_produces_empty_migration(self):
        schema = Schema("v1", [Table("users", [Column("id", "integer", primary_key=True)])])
        differ = SchemaDiffer()
        diff = differ.diff(schema, schema)
        generator = MigrationGenerator(dialect="postgresql")
        migration = generator.generate(diff, old_schema=schema, new_schema=schema)

        assert len(migration.steps) == 0

    def test_complex_migration(self):
        """Test a complex migration with multiple change types."""
        old = Schema("v1", [
            Table("users", [
                Column("id", "integer", primary_key=True),
                Column("name", "varchar", nullable=False),
                Column("age", "integer"),
            ]),
            Table("old_table", [Column("id", "integer", primary_key=True)]),
        ])
        new = Schema("v2", [
            Table("users", [
                Column("id", "integer", primary_key=True),
                Column("name", "varchar", nullable=False),
                Column("bio", "text"),  # Added, age removed
            ]),
            Table("new_table", [  # New table, old_table removed
                Column("id", "integer", primary_key=True),
                Column("value", "varchar"),
            ]),
        ])

        differ = SchemaDiffer()
        diff = differ.diff(old, new)
        generator = MigrationGenerator(dialect="postgresql")
        migration = generator.generate(diff, old_schema=old, new_schema=new)

        sql = migration.up_sql
        assert "DROP" in sql or "drop" in sql.lower()
        assert "ADD COLUMN" in sql or "CREATE TABLE" in sql
