"""Tests for sqlguard.schema module."""

import pytest
from sqlguard.schema import (
    Schema,
    Table,
    Column,
    ColumnType,
    ForeignKey,
    Index,
    CheckConstraint,
    UniqueConstraint,
)


class TestColumnType:
    """Tests for ColumnType enum and parsing."""

    def test_from_string_basic(self):
        assert ColumnType.from_string("integer") == ColumnType.INTEGER
        assert ColumnType.from_string("varchar") == ColumnType.VARCHAR
        assert ColumnType.from_string("boolean") == ColumnType.BOOLEAN
        assert ColumnType.from_string("timestamp") == ColumnType.TIMESTAMP

    def test_from_string_aliases(self):
        assert ColumnType.from_string("int") == ColumnType.INTEGER
        assert ColumnType.from_string("str") == ColumnType.VARCHAR
        assert ColumnType.from_string("bool") == ColumnType.BOOLEAN
        assert ColumnType.from_string("float") == ColumnType.REAL
        assert ColumnType.from_string("datetime") == ColumnType.TIMESTAMP
        assert ColumnType.from_string("string") == ColumnType.VARCHAR
        assert ColumnType.from_string("int8") == ColumnType.BIGINT
        assert ColumnType.from_string("float8") == ColumnType.DOUBLE_PRECISION
        assert ColumnType.from_string("double") == ColumnType.DOUBLE_PRECISION

    def test_from_string_case_insensitive(self):
        assert ColumnType.from_string("INTEGER") == ColumnType.INTEGER
        assert ColumnType.from_string("VarChar") == ColumnType.VARCHAR
        assert ColumnType.from_string("BOOLEAN") == ColumnType.BOOLEAN

    def test_from_string_with_params(self):
        assert ColumnType.from_string("varchar(255)") == ColumnType.VARCHAR
        assert ColumnType.from_string("decimal(10,2)") == ColumnType.DECIMAL

    def test_from_string_custom(self):
        result = ColumnType.from_string("custom_type")
        assert result == ColumnType.CUSTOM

    def test_from_string_whitespace(self):
        assert ColumnType.from_string("  integer  ") == ColumnType.INTEGER


class TestColumn:
    """Tests for Column dataclass."""

    def test_basic_creation(self):
        col = Column("id", "integer", primary_key=True)
        assert col.name == "id"
        assert col.base_type == ColumnType.INTEGER
        assert col.primary_key is True
        assert col.nullable is True  # Default

    def test_type_from_string(self):
        col = Column("email", "varchar", nullable=False)
        assert col.base_type == ColumnType.VARCHAR
        assert col.nullable is False

    def test_type_string(self):
        col = Column("name", "varchar")
        assert col.type_string == "varchar(255)"  # Default params

        col2 = Column("age", "integer")
        assert col2.type_string == "integer"

        col3 = Column("price", "decimal")
        assert col3.type_string == "decimal(10,2)"  # Default params

        col4 = Column("bio", "varchar", type_params="500")
        assert col4.type_string == "varchar(500)"

    def test_reference_parsing(self):
        col = Column("user_id", "integer", references="users.id")
        assert col.reference_table == "users"
        assert col.reference_column == "id"

    def test_reference_no_column(self):
        col = Column("user_id", "integer", references="users")
        assert col.reference_table == "users"
        assert col.reference_column == "id"  # Default

    def test_no_reference(self):
        col = Column("name", "varchar")
        assert col.reference_table is None
        assert col.reference_column is None

    def test_equality(self):
        col1 = Column("id", "integer", primary_key=True)
        col2 = Column("id", "integer", primary_key=True)
        assert col1 == col2

    def test_inequality(self):
        col1 = Column("id", "integer", primary_key=True)
        col2 = Column("id", "varchar")
        assert col1 != col2

    def test_is_breaking_change_type_change(self):
        old = Column("age", "integer")
        new = Column("age", "varchar")
        breaking, desc = new.is_breaking_change_from(old)
        assert breaking is True
        assert "type changed" in desc

    def test_is_breaking_change_type_widening(self):
        old = Column("id", "smallint")
        new = Column("id", "integer")
        breaking, desc = new.is_breaking_change_from(old)
        assert breaking is False
        assert "widened" in desc

    def test_is_breaking_change_nullable_to_not_null(self):
        old = Column("name", "varchar", nullable=True)
        new = Column("name", "varchar", nullable=False)
        breaking, desc = new.is_breaking_change_from(old)
        assert breaking is True
        assert "NOT NULL" in desc

    def test_is_breaking_change_not_null_to_nullable(self):
        old = Column("name", "varchar", nullable=False)
        new = Column("name", "varchar", nullable=True)
        breaking, desc = new.is_breaking_change_from(old)
        assert breaking is False

    def test_is_breaking_change_add_unique(self):
        old = Column("email", "varchar", unique=False)
        new = Column("email", "varchar", unique=True)
        breaking, desc = new.is_breaking_change_from(old)
        assert breaking is True

    def test_is_breaking_change_no_change(self):
        old = Column("name", "varchar")
        new = Column("name", "varchar")
        breaking, desc = new.is_breaking_change_from(old)
        assert breaking is False
        assert desc == "no changes"

    def test_hash(self):
        col1 = Column("id", "integer", primary_key=True)
        col2 = Column("id", "integer", primary_key=True)
        assert hash(col1) == hash(col2)


class TestTable:
    """Tests for Table dataclass."""

    def test_basic_creation(self):
        table = Table("users", [
            Column("id", "integer", primary_key=True),
            Column("name", "varchar", nullable=False),
        ])
        assert table.name == "users"
        assert len(table.columns) == 2

    def test_get_column(self):
        table = Table("users", [
            Column("id", "integer", primary_key=True),
            Column("email", "varchar"),
        ])
        assert table.get_column("id") is not None
        assert table.get_column("email") is not None
        assert table.get_column("nonexistent") is None

    def test_get_column_case_insensitive(self):
        table = Table("users", [Column("ID", "integer", primary_key=True)])
        assert table.get_column("id") is not None
        assert table.get_column("ID") is not None
        assert table.get_column("Id") is not None

    def test_primary_key_columns(self):
        table = Table("users", [
            Column("id", "integer", primary_key=True),
            Column("name", "varchar"),
        ])
        pks = table.primary_key_columns
        assert len(pks) == 1
        assert pks[0].name == "id"

    def test_column_names(self):
        table = Table("users", [
            Column("id", "integer"),
            Column("name", "varchar"),
        ])
        assert table.column_names == ["id", "name"]

    def test_add_column(self):
        table = Table("users", [Column("id", "integer")])
        table.add_column(Column("name", "varchar"))
        assert len(table.columns) == 2

    def test_add_duplicate_column(self):
        table = Table("users", [Column("id", "integer")])
        with pytest.raises(ValueError, match="already exists"):
            table.add_column(Column("id", "varchar"))

    def test_remove_column(self):
        table = Table("users", [
            Column("id", "integer"),
            Column("name", "varchar"),
        ])
        removed = table.remove_column("name")
        assert removed.name == "name"
        assert len(table.columns) == 1

    def test_remove_nonexistent_column(self):
        table = Table("users", [Column("id", "integer")])
        with pytest.raises(ValueError, match="not found"):
            table.remove_column("nonexistent")

    def test_equality(self):
        t1 = Table("users")
        t2 = Table("Users")
        assert t1 == t2  # Case-insensitive

    def test_hash(self):
        t1 = Table("users")
        t2 = Table("users")
        assert hash(t1) == hash(t2)


class TestSchema:
    """Tests for Schema dataclass."""

    def _make_schema(self) -> Schema:
        return Schema("my_app", [
            Table("users", [
                Column("id", "integer", primary_key=True),
                Column("email", "varchar", nullable=False, unique=True),
                Column("name", "varchar", nullable=False),
            ]),
            Table("posts", [
                Column("id", "integer", primary_key=True),
                Column("user_id", "integer", nullable=False, references="users.id"),
                Column("title", "varchar", nullable=False),
                Column("body", "text"),
            ]),
        ])

    def test_basic_creation(self):
        schema = self._make_schema()
        assert schema.name == "my_app"
        assert len(schema.tables) == 2

    def test_get_table(self):
        schema = self._make_schema()
        assert schema.get_table("users") is not None
        assert schema.get_table("posts") is not None
        assert schema.get_table("nonexistent") is None

    def test_get_table_case_insensitive(self):
        schema = self._make_schema()
        assert schema.get_table("Users") is not None
        assert schema.get_table("USERS") is not None

    def test_table_names(self):
        schema = self._make_schema()
        assert "users" in schema.table_names
        assert "posts" in schema.table_names

    def test_add_table(self):
        schema = self._make_schema()
        schema.add_table(Table("comments", [Column("id", "integer", primary_key=True)]))
        assert len(schema.tables) == 3

    def test_add_duplicate_table(self):
        schema = self._make_schema()
        with pytest.raises(ValueError, match="already exists"):
            schema.add_table(Table("users", []))

    def test_remove_table(self):
        schema = self._make_schema()
        removed = schema.remove_table("posts")
        assert removed.name == "posts"
        assert len(schema.tables) == 1

    def test_remove_nonexistent_table(self):
        schema = self._make_schema()
        with pytest.raises(ValueError, match="not found"):
            schema.remove_table("nonexistent")

    def test_all_columns(self):
        schema = self._make_schema()
        all_cols = schema.all_columns()
        assert "users" in all_cols
        assert "posts" in all_cols
        assert "id" in all_cols["users"]
        assert "email" in all_cols["users"]

    def test_all_foreign_keys(self):
        schema = self._make_schema()
        fks = schema.all_foreign_keys()
        # Should find the column-level FK from posts.user_id
        assert len(fks) >= 1
        fk_tables = [fk.reference_table for fk in fks]
        assert "users" in fk_tables

    def test_validate_no_issues(self):
        schema = self._make_schema()
        issues = schema.validate()
        assert len(issues) == 0

    def test_validate_missing_referenced_table(self):
        schema = Schema("bad", [
            Table("orders", [
                Column("id", "integer", primary_key=True),
                Column("product_id", "integer", references="products.id"),
            ]),
        ])
        issues = schema.validate()
        assert any("non-existent table" in i for i in issues)

    def test_validate_duplicate_column(self):
        table = Table("users", [
            Column("id", "integer", primary_key=True),
            Column("id", "varchar"),  # Duplicate!
        ])
        schema = Schema("bad", [table])
        issues = schema.validate()
        assert any("duplicate column" in i for i in issues)

    def test_validate_missing_primary_key(self):
        schema = Schema("no_pk", [
            Table("data", [
                Column("value", "varchar"),
            ]),
        ])
        issues = schema.validate()
        assert any("no primary key" in i for i in issues)

    def test_to_dict_and_from_dict(self):
        schema = self._make_schema()
        d = schema.to_dict()
        restored = Schema.from_dict(d)
        assert restored.name == schema.name
        assert len(restored.tables) == len(schema.tables)
        assert len(restored.tables[0].columns) == len(schema.tables[0].columns)

    def test_copy(self):
        schema = self._make_schema()
        copy = schema.copy()
        assert copy.name == schema.name
        # Verify deep copy
        copy.tables[0].columns[0].name = "modified"
        assert schema.tables[0].columns[0].name == "id"

    def test_foreign_key_with_index(self):
        schema = Schema("indexed", [
            Table("users", [
                Column("id", "integer", primary_key=True),
            ], indexes=[
                Index("idx_users_email", "users", ["email"], unique=True),
            ]),
        ])
        issues = schema.validate()
        assert any("non-existent column" in i for i in issues)


class TestForeignKey:
    """Tests for ForeignKey."""

    def test_equality(self):
        fk1 = ForeignKey("fk_1", ["user_id"], "users", ["id"])
        fk2 = ForeignKey("fk_2", ["user_id"], "users", ["id"])
        assert fk1 == fk2  # Same columns and references

    def test_inequality(self):
        fk1 = ForeignKey("fk_1", ["user_id"], "users", ["id"])
        fk2 = ForeignKey("fk_2", ["order_id"], "orders", ["id"])
        assert fk1 != fk2


class TestIndex:
    """Tests for Index."""

    def test_equality(self):
        i1 = Index("idx1", "users", ["email"], unique=True)
        i2 = Index("idx2", "users", ["email"], unique=True)
        assert i1 == i2

    def test_inequality(self):
        i1 = Index("idx1", "users", ["email"])
        i2 = Index("idx2", "users", ["name"])
        assert i1 != i2


class TestConstraints:
    """Tests for CheckConstraint and UniqueConstraint."""

    def test_check_equality(self):
        c1 = CheckConstraint("chk1", "users", "age > 0")
        c2 = CheckConstraint("chk2", "users", "age > 0")
        assert c1 == c2

    def test_unique_constraint_equality(self):
        u1 = UniqueConstraint("uc1", "users", ["email", "tenant_id"])
        u2 = UniqueConstraint("uc2", "users", ["email", "tenant_id"])
        assert u1 == u2
