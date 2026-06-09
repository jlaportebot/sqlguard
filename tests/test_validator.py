"""Tests for sqlguard.validator module."""

from sqlguard.schema import Column, Schema, Table
from sqlguard.validator import QueryValidator, ValidationError


class TestQueryValidator:
    """Tests for query validation against a schema."""

    def _make_schema(self) -> Schema:
        return Schema(
            "my_app",
            [
                Table(
                    "users",
                    [
                        Column("id", "integer", primary_key=True),
                        Column("email", "varchar", nullable=False, unique=True),
                        Column("name", "varchar", nullable=False),
                        Column("active", "boolean", default="true"),
                    ],
                ),
                Table(
                    "posts",
                    [
                        Column("id", "integer", primary_key=True),
                        Column("user_id", "integer", nullable=False, references="users.id"),
                        Column("title", "varchar", nullable=False),
                        Column("body", "text"),
                        Column("published", "boolean", default="false"),
                    ],
                ),
                Table(
                    "comments",
                    [
                        Column("id", "integer", primary_key=True),
                        Column("post_id", "integer", nullable=False, references="posts.id"),
                        Column("author_id", "integer", nullable=False, references="users.id"),
                        Column("content", "text", nullable=False),
                    ],
                ),
            ],
        )

    def setup_method(self):
        self.schema = self._make_schema()
        self.validator = QueryValidator(self.schema)

    def test_valid_simple_query(self):
        errors = self.validator.validate("SELECT id, name FROM users WHERE active = true;")
        assert len(errors) == 0

    def test_nonexistent_table(self):
        errors = self.validator.validate("SELECT * FROM nonexistent_table;")
        table_errors = [e for e in errors if "nonexistent_table" in e.message.lower()]
        assert len(table_errors) >= 1

    def test_nonexistent_column(self):
        errors = self.validator.validate("SELECT nonexistent_col FROM users;")
        col_errors = [e for e in errors if "nonexistent_col" in e.message.lower()]
        assert len(col_errors) >= 1

    def test_valid_table_column_reference(self):
        errors = self.validator.validate("SELECT users.id, users.email FROM users;")
        assert len(errors) == 0

    def test_invalid_table_column_reference(self):
        errors = self.validator.validate("SELECT users.nonexistent FROM users;")
        col_errors = [e for e in errors if "nonexistent" in e.message.lower()]
        assert len(col_errors) >= 1

    def test_join_query_valid(self):
        sql = """
        SELECT u.id, u.name, p.title
        FROM users u
        JOIN posts p ON u.id = p.user_id
        WHERE u.active = true;
        """
        errors = self.validator.validate(sql)
        # Should not have errors about valid columns
        critical_errors = [e for e in errors if e.severity == "error"]
        assert len(critical_errors) == 0

    def test_ambiguous_column(self):
        # Both users and comments have 'id' column
        # If we reference 'id' without table prefix in a multi-table query, it's ambiguous
        sql = """
        SELECT id FROM users JOIN comments ON users.id = comments.author_id;
        """
        errors = self.validator.validate(sql)
        ambiguous = [e for e in errors if "ambiguous" in e.message.lower()]
        assert len(ambiguous) >= 1

    def test_update_valid(self):
        errors = self.validator.validate("UPDATE users SET name = 'test' WHERE id = 1;")
        assert len(errors) == 0

    def test_insert_valid(self):
        errors = self.validator.validate(
            "INSERT INTO users (id, email, name) VALUES (1, 'a@b.com', 'Test');"
        )
        assert len(errors) == 0

    def test_delete_valid(self):
        errors = self.validator.validate("DELETE FROM posts WHERE id = 1;")
        assert len(errors) == 0

    def test_empty_query(self):
        errors = self.validator.validate("")
        assert len(errors) == 0

    def test_validation_error_str(self):
        err = ValidationError(message="Column 'foo' not found", table="users", column="foo")
        s = str(err)
        assert "[error]" in s
        assert "foo" in s

    def test_validation_error_to_dict(self):
        err = ValidationError(
            message="Column 'foo' not found", table="users", column="foo", line=5, severity="error"
        )
        d = err.to_dict()
        assert d["message"] == "Column 'foo' not found"
        assert d["table"] == "users"
        assert d["column"] == "foo"
        assert d["line"] == 5

    def test_multiple_table_query_with_alias(self):
        sql = """
        SELECT u.name, p.title, c.content
        FROM users u
        JOIN posts p ON u.id = p.user_id
        JOIN comments c ON p.id = c.post_id;
        """
        errors = self.validator.validate(sql)
        critical_errors = [e for e in errors if e.severity == "error"]
        assert len(critical_errors) == 0

    def test_order_by_valid_column(self):
        errors = self.validator.validate("SELECT id, name FROM users ORDER BY name;")
        critical_errors = [e for e in errors if e.severity == "error"]
        assert len(critical_errors) == 0

    def test_group_by_valid_column(self):
        errors = self.validator.validate("SELECT active, COUNT(*) FROM users GROUP BY active;")
        critical_errors = [e for e in errors if e.severity == "error"]
        assert len(critical_errors) == 0

    def test_case_insensitive_table_names(self):
        errors = self.validator.validate("SELECT id FROM USERS;")
        critical_errors = [e for e in errors if "does not exist" in e.message]
        assert len(critical_errors) == 0
