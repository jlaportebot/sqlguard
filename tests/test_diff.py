"""Tests for sqlguard.diff module."""

import pytest
from sqlguard.schema import Schema, Table, Column, ForeignKey, Index, CheckConstraint, UniqueConstraint
from sqlguard.diff import SchemaDiffer, SchemaDiff, ChangeType, Change


class TestSchemaDiffer:
    """Tests for schema diffing."""

    def _make_old_schema(self) -> Schema:
        return Schema("v1", [
            Table("users", [
                Column("id", "integer", primary_key=True),
                Column("email", "varchar", nullable=False, unique=True),
                Column("name", "varchar", nullable=False),
                Column("age", "integer"),
            ]),
            Table("posts", [
                Column("id", "integer", primary_key=True),
                Column("user_id", "integer", nullable=False, references="users.id"),
                Column("title", "varchar", nullable=False),
                Column("body", "text"),
            ]),
        ])

    def _make_new_schema(self) -> Schema:
        return Schema("v2", [
            Table("users", [
                Column("id", "integer", primary_key=True),
                Column("email", "varchar", nullable=False, unique=True),
                Column("name", "varchar", nullable=False),
                Column("age", "integer"),
                Column("avatar_url", "varchar", nullable=True),  # Added
            ]),
            Table("posts", [
                Column("id", "integer", primary_key=True),
                Column("user_id", "integer", nullable=False, references="users.id"),
                Column("title", "varchar", nullable=False),
                Column("body", "text"),
                Column("published", "boolean", default="false"),  # Added
            ]),
            Table("comments", [  # New table
                Column("id", "integer", primary_key=True),
                Column("post_id", "integer", nullable=False, references="posts.id"),
                Column("author_id", "integer", nullable=False, references="users.id"),
                Column("content", "text", nullable=False),
                Column("created_at", "timestamp", default="now()"),
            ]),
        ])

    def test_no_changes(self):
        schema = self._make_old_schema()
        differ = SchemaDiffer()
        diff = differ.diff(schema, schema)
        assert len(diff.changes) == 0
        assert not diff.has_breaking_changes

    def test_table_added(self):
        old = self._make_old_schema()
        new = self._make_new_schema()
        differ = SchemaDiffer()
        diff = differ.diff(old, new)

        table_adds = diff.tables_added
        assert len(table_adds) == 1
        assert table_adds[0].table == "comments"
        assert not table_adds[0].breaking

    def test_table_removed(self):
        old = self._make_new_schema()
        new = self._make_old_schema()
        differ = SchemaDiffer()
        diff = differ.diff(old, new)

        table_removes = diff.tables_removed
        assert len(table_removes) == 1
        assert table_removes[0].table == "comments"
        assert table_removes[0].breaking

    def test_column_added_nullable(self):
        old = self._make_old_schema()
        new = self._make_new_schema()
        differ = SchemaDiffer()
        diff = differ.diff(old, new)

        col_adds = diff.columns_added
        assert len(col_adds) >= 2  # avatar_url and published

        # Nullable column with default is safe
        avatar_add = [c for c in col_adds if c.column == "avatar_url"]
        assert len(avatar_add) == 1
        assert not avatar_add[0].breaking

    def test_column_added_not_null_without_default(self):
        old = Schema("v1", [Table("t", [Column("id", "integer", primary_key=True)])])
        new = Schema("v2", [Table("t", [
            Column("id", "integer", primary_key=True),
            Column("name", "varchar", nullable=False),  # NOT NULL, no default — BREAKING
        ])])
        differ = SchemaDiffer()
        diff = differ.diff(old, new)

        col_adds = [c for c in diff.columns_added if c.column == "name"]
        assert len(col_adds) == 1
        assert col_adds[0].breaking

    def test_column_added_not_null_with_default(self):
        old = Schema("v1", [Table("t", [Column("id", "integer", primary_key=True)])])
        new = Schema("v2", [Table("t", [
            Column("id", "integer", primary_key=True),
            Column("active", "boolean", nullable=False, default="true"),
        ])])
        differ = SchemaDiffer()
        diff = differ.diff(old, new)

        col_adds = [c for c in diff.columns_added if c.column == "active"]
        assert len(col_adds) == 1
        assert not col_adds[0].breaking  # Has default, so safe

    def test_column_removed(self):
        old = self._make_old_schema()
        new = Schema("v2", [
            Table("users", [
                Column("id", "integer", primary_key=True),
                Column("email", "varchar", nullable=False, unique=True),
                Column("name", "varchar", nullable=False),
                # "age" column removed
            ]),
        ])
        differ = SchemaDiffer()
        diff = differ.diff(old, new)

        col_removes = diff.columns_removed
        assert len(col_removes) == 1
        assert col_removes[0].column == "age"
        assert col_removes[0].breaking

    def test_column_type_change_breaking(self):
        old = Schema("v1", [Table("t", [Column("id", "integer", primary_key=True), Column("val", "integer")])])
        new = Schema("v2", [Table("t", [Column("id", "integer", primary_key=True), Column("val", "varchar")])])
        differ = SchemaDiffer()
        diff = differ.diff(old, new)

        type_changes = [c for c in diff.changes if c.change_type == ChangeType.COLUMN_TYPE_CHANGED]
        assert len(type_changes) == 1
        assert type_changes[0].breaking

    def test_column_type_widening_safe(self):
        old = Schema("v1", [Table("t", [Column("id", "integer", primary_key=True), Column("val", "smallint")])])
        new = Schema("v2", [Table("t", [Column("id", "integer", primary_key=True), Column("val", "integer")])])
        differ = SchemaDiffer()
        diff = differ.diff(old, new)

        type_changes = [c for c in diff.changes if c.change_type == ChangeType.COLUMN_TYPE_CHANGED]
        assert len(type_changes) == 1
        assert not type_changes[0].breaking

    def test_nullable_to_not_null_breaking(self):
        old = Schema("v1", [Table("t", [Column("id", "integer", primary_key=True), Column("name", "varchar", nullable=True)])])
        new = Schema("v2", [Table("t", [Column("id", "integer", primary_key=True), Column("name", "varchar", nullable=False)])])
        differ = SchemaDiffer()
        diff = differ.diff(old, new)

        null_changes = [c for c in diff.changes if c.change_type == ChangeType.COLUMN_NULLABILITY_CHANGED]
        assert len(null_changes) == 1
        assert null_changes[0].breaking

    def test_not_null_to_nullable_safe(self):
        old = Schema("v1", [Table("t", [Column("id", "integer", primary_key=True), Column("name", "varchar", nullable=False)])])
        new = Schema("v2", [Table("t", [Column("id", "integer", primary_key=True), Column("name", "varchar", nullable=True)])])
        differ = SchemaDiffer()
        diff = differ.diff(old, new)

        null_changes = [c for c in diff.changes if c.change_type == ChangeType.COLUMN_NULLABILITY_CHANGED]
        assert len(null_changes) == 1
        assert not null_changes[0].breaking

    def test_default_removed_breaking(self):
        old = Schema("v1", [Table("t", [Column("id", "integer", primary_key=True), Column("status", "varchar", default="'active'")])])
        new = Schema("v2", [Table("t", [Column("id", "integer", primary_key=True), Column("status", "varchar", default=None)])])
        differ = SchemaDiffer()
        diff = differ.diff(old, new)

        default_changes = [c for c in diff.changes if c.change_type == ChangeType.COLUMN_DEFAULT_CHANGED]
        assert len(default_changes) == 1
        assert default_changes[0].breaking

    def test_default_added_safe(self):
        old = Schema("v1", [Table("t", [Column("id", "integer", primary_key=True), Column("status", "varchar")])])
        new = Schema("v2", [Table("t", [Column("id", "integer", primary_key=True), Column("status", "varchar", default="'active'")])])
        differ = SchemaDiffer()
        diff = differ.diff(old, new)

        default_changes = [c for c in diff.changes if c.change_type == ChangeType.COLUMN_DEFAULT_CHANGED]
        assert len(default_changes) == 1
        assert not default_changes[0].breaking

    def test_foreign_key_added_and_removed(self):
        old = Schema("v1", [
            Table("users", [Column("id", "integer", primary_key=True)]),
            Table("posts", [
                Column("id", "integer", primary_key=True),
                Column("user_id", "integer", references="users.id"),
            ], foreign_keys=[
                ForeignKey("fk_posts_user", ["user_id"], "users", ["id"]),
            ]),
        ])
        new = Schema("v2", [
            Table("users", [Column("id", "integer", primary_key=True)]),
            Table("posts", [
                Column("id", "integer", primary_key=True),
                Column("user_id", "integer"),
            ]),
        ])
        differ = SchemaDiffer()
        diff = differ.diff(old, new)

        fk_removed = [c for c in diff.changes if c.change_type == ChangeType.FOREIGN_KEY_REMOVED]
        assert len(fk_removed) == 1
        assert fk_removed[0].breaking

    def test_index_changes(self):
        old = Schema("v1", [
            Table("users", [
                Column("id", "integer", primary_key=True),
                Column("email", "varchar"),
            ], indexes=[
                Index("idx_users_email", "users", ["email"]),
            ]),
        ])
        new = Schema("v2", [
            Table("users", [
                Column("id", "integer", primary_key=True),
                Column("email", "varchar"),
                Column("name", "varchar"),
            ], indexes=[
                Index("idx_users_name", "users", ["name"]),
            ]),
        ])
        differ = SchemaDiffer()
        diff = differ.diff(old, new)

        idx_added = [c for c in diff.changes if c.change_type == ChangeType.INDEX_ADDED]
        idx_removed = [c for c in diff.changes if c.change_type == ChangeType.INDEX_REMOVED]
        assert len(idx_added) == 1
        assert len(idx_removed) == 1

    def test_check_constraint_changes(self):
        old = Schema("v1", [
            Table("users", [
                Column("id", "integer", primary_key=True),
                Column("age", "integer"),
            ], checks=[
                CheckConstraint("chk_age", "users", "age >= 0"),
            ]),
        ])
        new = Schema("v2", [
            Table("users", [
                Column("id", "integer", primary_key=True),
                Column("age", "integer"),
            ]),
        ])
        differ = SchemaDiffer()
        diff = differ.diff(old, new)

        check_removed = [c for c in diff.changes if c.change_type == ChangeType.CHECK_REMOVED]
        assert len(check_removed) == 1
        assert not check_removed[0].breaking

    def test_unique_constraint_changes(self):
        old = Schema("v1", [
            Table("users", [
                Column("id", "integer", primary_key=True),
                Column("email", "varchar"),
                Column("tenant_id", "integer"),
            ], unique_constraints=[
                UniqueConstraint("uc_email_tenant", "users", ["email", "tenant_id"]),
            ]),
        ])
        new = Schema("v2", [
            Table("users", [
                Column("id", "integer", primary_key=True),
                Column("email", "varchar"),
                Column("tenant_id", "integer"),
            ]),
        ])
        differ = SchemaDiffer()
        diff = differ.diff(old, new)

        uc_removed = [c for c in diff.changes if c.change_type == ChangeType.UNIQUE_CONSTRAINT_REMOVED]
        assert len(uc_removed) == 1
        assert not uc_removed[0].breaking

    def test_diff_summary(self):
        old = self._make_old_schema()
        new = self._make_new_schema()
        differ = SchemaDiffer()
        diff = differ.diff(old, new)

        summary = diff.summary()
        assert "v1" in summary
        assert "v2" in summary
        assert "Total changes" in summary

    def test_diff_to_dict(self):
        old = self._make_old_schema()
        new = self._make_new_schema()
        differ = SchemaDiffer()
        diff = differ.diff(old, new)

        d = diff.to_dict()
        assert d["old_schema"] == "v1"
        assert d["new_schema"] == "v2"
        assert isinstance(d["changes"], list)

    def test_change_str(self):
        change = Change(
            change_type=ChangeType.COLUMN_REMOVED,
            table="users",
            column="age",
            breaking=True,
            description="column 'age' removed",
        )
        s = str(change)
        assert "BREAKING" in s
        assert "users.age" in s

    def test_safe_change_str(self):
        change = Change(
            change_type=ChangeType.COLUMN_ADDED,
            table="users",
            column="avatar_url",
            breaking=False,
            description="column added",
        )
        s = str(change)
        assert "SAFE" in s
