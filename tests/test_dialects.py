"""Tests for sqlguard.dialects module."""

import pytest

from sqlguard.dialects import MysqlDialect, PostgresqlDialect, SqliteDialect, get_dialect
from sqlguard.schema import CheckConstraint, Column, ForeignKey, Index, UniqueConstraint


class TestPostgresqlDialect:
    """Tests for PostgreSQL dialect rendering."""

    def setup_method(self):
        self.dialect = PostgresqlDialect()

    def test_render_column_type_integer(self):
        col = Column("id", "integer")
        assert self.dialect.render_column_type(col) == "INTEGER"

    def test_render_column_type_varchar_with_params(self):
        col = Column("name", "varchar", type_params="100")
        assert self.dialect.render_column_type(col) == "VARCHAR(100)"

    def test_render_column_type_varchar_default(self):
        col = Column("name", "varchar")
        assert self.dialect.render_column_type(col) == "VARCHAR(255)"

    def test_render_column_type_decimal_default(self):
        col = Column("price", "decimal")
        assert self.dialect.render_column_type(col) == "DECIMAL(10,2)"

    def test_render_column_type_uuid(self):
        col = Column("id", "uuid")
        assert self.dialect.render_column_type(col) == "UUID"

    def test_render_column_type_jsonb(self):
        col = Column("data", "jsonb")
        assert self.dialect.render_column_type(col) == "JSONB"

    def test_render_column_type_bytea(self):
        col = Column("data", "bytea")
        assert self.dialect.render_column_type(col) == "BYTEA"

    def test_render_column_constraints(self):
        col = Column("email", "varchar", nullable=False, unique=True)
        constraints = self.dialect.render_column_constraints(col)
        assert "NOT NULL" in constraints
        assert "UNIQUE" in constraints

    def test_render_column_constraints_with_default(self):
        col = Column("active", "boolean", default="true")
        constraints = self.dialect.render_column_constraints(col)
        assert "DEFAULT true" in constraints

    def test_render_column_constraints_with_fk(self):
        col = Column("user_id", "integer", references="users.id")
        constraints = self.dialect.render_column_constraints(col)
        assert "REFERENCES users(id)" in constraints

    def test_render_column_definition(self):
        col = Column("id", "integer", primary_key=True)
        definition = self.dialect.render_column_definition(col)
        assert "id" in definition
        assert "INTEGER" in definition
        assert "PRIMARY KEY" in definition

    def test_render_column_definition_full(self):
        col = Column("email", "varchar", nullable=False, unique=True, default="'none@example.com'")
        definition = self.dialect.render_column_definition(col)
        assert "email" in definition
        assert "NOT NULL" in definition
        assert "UNIQUE" in definition
        assert "DEFAULT" in definition

    def test_render_add_column(self):
        col = Column("bio", "text", nullable=True)
        sql = self.dialect.render_add_column("users", col)
        assert "ALTER TABLE users ADD COLUMN" in sql
        assert "bio" in sql

    def test_render_drop_column(self):
        sql = self.dialect.render_drop_column("users", "age")
        assert "ALTER TABLE users DROP COLUMN age" in sql

    def test_render_alter_column_type(self):
        col = Column("age", "varchar")
        sql = self.dialect.render_alter_column_type("users", col)
        assert "ALTER TABLE users ALTER COLUMN age TYPE VARCHAR(255)" in sql
        assert "USING" in sql  # PostgreSQL-specific

    def test_render_alter_column_nullable(self):
        sql = self.dialect.render_alter_column_nullability("users", "name", True)
        assert "DROP NOT NULL" in sql

        sql = self.dialect.render_alter_column_nullability("users", "name", False)
        assert "SET NOT NULL" in sql

    def test_render_alter_column_default(self):
        sql = self.dialect.render_alter_column_default("users", "status", "'active'")
        assert "SET DEFAULT 'active'" in sql

        sql = self.dialect.render_alter_column_default("users", "status", None)
        assert "DROP DEFAULT" in sql

    def test_render_create_table(self):
        columns = [
            Column("id", "integer", primary_key=True),
            Column("name", "varchar", nullable=False),
            Column("email", "varchar", unique=True),
        ]
        sql = self.dialect.render_create_table("users", columns)
        assert "CREATE TABLE users" in sql
        assert "id" in sql
        assert "name" in sql
        assert "email" in sql
        assert "PRIMARY KEY" in sql

    def test_render_foreign_key(self):
        fk = ForeignKey("fk_posts_user", ["user_id"], "users", ["id"], on_delete="CASCADE")
        sql = self.dialect.render_foreign_key(fk, "posts")
        assert "ALTER TABLE posts ADD CONSTRAINT fk_posts_user" in sql
        assert "FOREIGN KEY (user_id)" in sql
        assert "REFERENCES users(id)" in sql
        assert "ON DELETE CASCADE" in sql

    def test_render_index(self):
        idx = Index("idx_users_email", "users", ["email"], unique=True)
        sql = self.dialect.render_index(idx)
        assert "CREATE UNIQUE INDEX idx_users_email" in sql
        assert "ON users (email)" in sql

    def test_render_check_constraint(self):
        chk = CheckConstraint("chk_age", "users", "age >= 0")
        sql = self.dialect.render_check(chk)
        assert "ADD CONSTRAINT chk_age CHECK (age >= 0)" in sql

    def test_render_unique_constraint(self):
        uc = UniqueConstraint("uc_email_tenant", "users", ["email", "tenant_id"])
        sql = self.dialect.render_unique_constraint(uc)
        assert "ADD CONSTRAINT uc_email_tenant UNIQUE (email, tenant_id)" in sql

    def test_render_drop_table(self):
        sql = self.dialect.render_drop_table("users")
        assert "DROP TABLE users" in sql

    def test_render_drop_foreign_key(self):
        sql = self.dialect.render_drop_foreign_key("fk_name", "posts")
        assert "DROP CONSTRAINT fk_name" in sql


class TestMysqlDialect:
    """Tests for MySQL dialect rendering."""

    def setup_method(self):
        self.dialect = MysqlDialect()

    def test_render_column_type_integer(self):
        col = Column("id", "integer")
        assert self.dialect.render_column_type(col) == "INT"

    def test_render_column_type_uuid(self):
        col = Column("id", "uuid")
        assert self.dialect.render_column_type(col) == "CHAR(36)"

    def test_render_column_type_timestamptz(self):
        # MySQL doesn't have TIMESTAMPTZ, falls back to TIMESTAMP
        col = Column("created_at", "timestamptz")
        assert self.dialect.render_column_type(col) == "TIMESTAMP"

    def test_render_column_type_blob(self):
        col = Column("data", "blob")
        assert self.dialect.render_column_type(col) == "BLOB"

    def test_render_column_type_inet(self):
        col = Column("ip", "inet")
        assert self.dialect.render_column_type(col) == "VARCHAR(45)"

    def test_render_column_type_array(self):
        # MySQL uses JSON for arrays
        col = Column("tags", "array")
        assert self.dialect.render_column_type(col) == "JSON"

    def test_render_alter_column_type(self):
        col = Column("name", "varchar", nullable=False)
        sql = self.dialect.render_alter_column_type("users", col)
        assert "MODIFY COLUMN" in sql
        assert "name" in sql

    def test_render_drop_foreign_key(self):
        sql = self.dialect.render_drop_foreign_key("fk_name", "posts")
        assert "DROP FOREIGN KEY fk_name" in sql


class TestSqliteDialect:
    """Tests for SQLite dialect rendering."""

    def setup_method(self):
        self.dialect = SqliteDialect()

    def test_render_column_type_integer(self):
        col = Column("id", "integer")
        assert self.dialect.render_column_type(col) == "INTEGER"

    def test_render_column_type_varchar_maps_to_text(self):
        col = Column("name", "varchar")
        assert self.dialect.render_column_type(col) == "TEXT"

    def test_render_column_type_boolean_maps_to_integer(self):
        col = Column("active", "boolean")
        assert self.dialect.render_column_type(col) == "INTEGER"

    def test_render_column_type_uuid_maps_to_text(self):
        col = Column("id", "uuid")
        assert self.dialect.render_column_type(col) == "TEXT"

    def test_render_column_definition_with_autoincrement(self):
        col = Column("id", "integer", primary_key=True, auto_increment=True)
        definition = self.dialect.render_column_definition(col)
        assert "PRIMARY KEY AUTOINCREMENT" in definition

    def test_render_foreign_key_is_comment(self):
        fk = ForeignKey("fk_posts_user", ["user_id"], "users", ["id"])
        sql = self.dialect.render_foreign_key(fk, "posts")
        assert "-- SQLite: Cannot add foreign key" in sql

    def test_render_alter_column_type_is_comment(self):
        col = Column("age", "varchar")
        sql = self.dialect.render_alter_column_type("users", col)
        assert "-- SQLite:" in sql

    def test_render_add_column(self):
        col = Column("bio", "text")
        sql = self.dialect.render_add_column("users", col)
        assert "ALTER TABLE users ADD COLUMN bio TEXT" in sql

    def test_render_index(self):
        idx = Index("idx_users_email", "users", ["email"])
        sql = self.dialect.render_index(idx)
        assert "CREATE INDEX idx_users_email ON users (email)" in sql


class TestGetDialect:
    """Tests for dialect factory function."""

    def test_postgresql(self):
        assert isinstance(get_dialect("postgresql"), PostgresqlDialect)

    def test_postgres_alias(self):
        assert isinstance(get_dialect("postgres"), PostgresqlDialect)

    def test_pg_alias(self):
        assert isinstance(get_dialect("pg"), PostgresqlDialect)

    def test_mysql(self):
        assert isinstance(get_dialect("mysql"), MysqlDialect)

    def test_mariadb_alias(self):
        assert isinstance(get_dialect("mariadb"), MysqlDialect)

    def test_sqlite(self):
        assert isinstance(get_dialect("sqlite"), SqliteDialect)

    def test_unknown_dialect(self):
        with pytest.raises(ValueError, match="Unknown dialect"):
            get_dialect("oracle")

    def test_case_insensitive(self):
        assert isinstance(get_dialect("PostgreSQL"), PostgresqlDialect)
        assert isinstance(get_dialect("MySQL"), MysqlDialect)
