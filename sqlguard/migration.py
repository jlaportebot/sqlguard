"""Migration generation from schema diffs for SQLGuard.

Takes a SchemaDiff and generates ordered, executable SQL migration steps
using the appropriate dialect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlguard.diff import SchemaDiff, ChangeType
from sqlguard.dialects import Dialect, PostgresqlDialect, get_dialect
from sqlguard.schema import Column, Schema


@dataclass
class MigrationStep:
    """A single step in a migration, corresponding to one SQL statement."""

    sql: str
    change_type: ChangeType
    table: str
    column: Optional[str] = None
    reversible: bool = True
    rollback_sql: Optional[str] = None
    comment: Optional[str] = None

    def to_sql(self) -> str:
        """Return the SQL for this step, with optional comment."""
        parts: list[str] = []
        if self.comment:
            parts.append(f"-- {self.comment}")
        parts.append(self.sql)
        return "\n".join(parts)

    def to_rollback_sql(self) -> str:
        """Return the rollback SQL for this step."""
        if self.rollback_sql:
            parts: list[str] = []
            if self.comment:
                parts.append(f"-- Rollback: {self.comment}")
            parts.append(self.rollback_sql)
            return "\n".join(parts)
        return f"-- No automatic rollback available for: {self.sql}"


@dataclass
class Migration:
    """A complete migration with up and down steps."""

    name: str
    steps: list[MigrationStep] = field(default_factory=list)
    dialect: str = "postgresql"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def add_step(self, step: MigrationStep) -> None:
        """Add a step to the migration."""
        self.steps.append(step)

    @property
    def up_sql(self) -> str:
        """Return all UP migration SQL."""
        if not self.steps:
            return "-- No migration steps\n"
        header = f"-- Migration: {self.name}\n-- Dialect: {self.dialect}\n-- Created: {self.created_at}\n"
        body = "\n\n".join(step.to_sql() for step in self.steps)
        return header + body + "\n"

    @property
    def down_sql(self) -> str:
        """Return all DOWN (rollback) migration SQL, in reverse order."""
        if not self.steps:
            return "-- No migration steps\n"
        header = f"-- Rollback: {self.name}\n-- Dialect: {self.dialect}\n"
        body = "\n\n".join(
            step.to_rollback_sql() for step in reversed(self.steps)
        )
        return header + body + "\n"

    @property
    def has_breaking_steps(self) -> bool:
        """Whether any step corresponds to a breaking change."""
        breaking_types = {
            ChangeType.TABLE_REMOVED,
            ChangeType.COLUMN_REMOVED,
            ChangeType.COLUMN_TYPE_CHANGED,
            ChangeType.COLUMN_NULLABILITY_CHANGED,
            ChangeType.COLUMN_PRIMARY_KEY_CHANGED,
            ChangeType.COLUMN_UNIQUE_CHANGED,
        }
        return any(s.change_type in breaking_types for s in self.steps)

    def summary(self) -> str:
        """Return a summary of this migration."""
        lines: list[str] = []
        lines.append(f"Migration: {self.name}")
        lines.append(f"Steps: {len(self.steps)}")
        lines.append(f"Dialect: {self.dialect}")
        lines.append(f"Has breaking changes: {self.has_breaking_steps}")
        lines.append("")
        for i, step in enumerate(self.steps, 1):
            col_info = f".{step.column}" if step.column else ""
            lines.append(f"  {i}. [{step.change_type.value}] {step.table}{col_info}")
        return "\n".join(lines)


class MigrationGenerator:
    """Generates SQL migration scripts from a SchemaDiff."""

    def __init__(self, dialect: str = "postgresql") -> None:
        self.dialect: Dialect = get_dialect(dialect)
        self.dialect_name = dialect

    def generate(
        self,
        diff: SchemaDiff,
        old_schema: Optional[Schema] = None,
        new_schema: Optional[Schema] = None,
    ) -> Migration:
        """Generate a Migration from a SchemaDiff.

        Args:
            diff: The schema diff to generate migrations for.
            old_schema: The old schema (needed for rollback SQL).
            new_schema: The new schema (needed for column definitions).

        Returns:
            A Migration with ordered up and down steps.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        migration_name = f"{timestamp}_{diff.old_schema}_to_{diff.new_schema}"
        migration = Migration(
            name=migration_name,
            dialect=self.dialect_name,
        )

        # Order matters! We need to:
        # 1. Drop foreign keys first (to allow column drops)
        # 2. Drop indexes
        # 3. Drop unique constraints
        # 4. Drop check constraints
        # 5. Drop columns
        # 6. Drop tables
        # 7. Alter columns
        # 8. Add columns
        # 9. Add tables
        # 10. Add foreign keys
        # 11. Add indexes
        # 12. Add unique constraints
        # 13. Add check constraints

        # Categorize changes
        drop_fks = []
        drop_indexes = []
        drop_unique_constraints = []
        drop_checks = []
        drop_columns = []
        drop_tables = []
        alter_columns = []
        add_columns = []
        add_tables = []
        add_fks = []
        add_indexes = []
        add_unique_constraints = []
        add_checks = []

        for change in diff.changes:
            ct = change.change_type
            if ct == ChangeType.FOREIGN_KEY_REMOVED:
                drop_fks.append(change)
            elif ct == ChangeType.INDEX_REMOVED:
                drop_indexes.append(change)
            elif ct == ChangeType.UNIQUE_CONSTRAINT_REMOVED:
                drop_unique_constraints.append(change)
            elif ct == ChangeType.CHECK_REMOVED:
                drop_checks.append(change)
            elif ct == ChangeType.COLUMN_REMOVED:
                drop_columns.append(change)
            elif ct == ChangeType.TABLE_REMOVED:
                drop_tables.append(change)
            elif ct in (
                ChangeType.COLUMN_TYPE_CHANGED,
                ChangeType.COLUMN_NULLABILITY_CHANGED,
                ChangeType.COLUMN_DEFAULT_CHANGED,
                ChangeType.COLUMN_PRIMARY_KEY_CHANGED,
                ChangeType.COLUMN_UNIQUE_CHANGED,
                ChangeType.COLUMN_FOREIGN_KEY_CHANGED,
                ChangeType.COLUMN_AUTO_INCREMENT_CHANGED,
            ):
                alter_columns.append(change)
            elif ct == ChangeType.COLUMN_ADDED:
                add_columns.append(change)
            elif ct == ChangeType.TABLE_ADDED:
                add_tables.append(change)
            elif ct == ChangeType.FOREIGN_KEY_ADDED:
                add_fks.append(change)
            elif ct == ChangeType.FOREIGN_KEY_CHANGED:
                drop_fks.append(change)
                add_fks.append(change)
            elif ct == ChangeType.INDEX_ADDED:
                add_indexes.append(change)
            elif ct == ChangeType.INDEX_CHANGED:
                drop_indexes.append(change)
                add_indexes.append(change)
            elif ct == ChangeType.UNIQUE_CONSTRAINT_ADDED:
                add_unique_constraints.append(change)
            elif ct == ChangeType.CHECK_ADDED:
                add_checks.append(change)

        # Generate steps in order

        # 1. Drop foreign keys
        for change in drop_fks:
            if change.old_value:
                step = MigrationStep(
                    sql=self.dialect.render_drop_foreign_key(
                        change.old_value.split("→")[0].strip() if "→" in change.old_value else change.old_value,
                        change.table,
                    ),
                    change_type=change.change_type,
                    table=change.table,
                    comment=f"Drop FK: {change.description}",
                )
                migration.add_step(step)

        # 2. Drop indexes
        for change in drop_indexes:
            idx_name = change.old_value or change.new_value or "unknown"
            step = MigrationStep(
                sql=self.dialect.render_drop_index(idx_name),
                change_type=change.change_type,
                table=change.table,
                comment=f"Drop index: {change.description}",
            )
            migration.add_step(step)

        # 3. Drop unique constraints
        for change in drop_unique_constraints:
            step = MigrationStep(
                sql=self.dialect.render_drop_unique_constraint(
                    change.old_value or "unknown", change.table
                ),
                change_type=change.change_type,
                table=change.table,
                comment=f"Drop unique constraint: {change.description}",
            )
            migration.add_step(step)

        # 4. Drop check constraints
        for change in drop_checks:
            step = MigrationStep(
                sql=self.dialect.render_drop_check(
                    change.old_value or "unknown", change.table
                ),
                change_type=change.change_type,
                table=change.table,
                comment=f"Drop check constraint: {change.description}",
            )
            migration.add_step(step)

        # 5. Drop columns
        for change in drop_columns:
            step = MigrationStep(
                sql=self.dialect.render_drop_column(change.table, change.column or "unknown"),
                change_type=change.change_type,
                table=change.table,
                column=change.column,
                reversible=False,
                comment=f"Drop column: {change.description}",
            )
            migration.add_step(step)

        # 6. Drop tables
        for change in drop_tables:
            step = MigrationStep(
                sql=self.dialect.render_drop_table(change.table),
                change_type=change.change_type,
                table=change.table,
                reversible=False,
                comment=f"Drop table: {change.description}",
            )
            migration.add_step(step)

        # 7. Alter columns
        for change in alter_columns:
            self._generate_alter_column_steps(change, new_schema, migration)

        # 8. Add columns
        for change in add_columns:
            if new_schema:
                table = new_schema.get_table(change.table)
                if table and change.column:
                    col = table.get_column(change.column)
                    if col:
                        step = MigrationStep(
                            sql=self.dialect.render_add_column(change.table, col),
                            change_type=change.change_type,
                            table=change.table,
                            column=change.column,
                            comment=f"Add column: {change.description}",
                        )
                        migration.add_step(step)
                        continue
            # Fallback: simple ADD COLUMN without full type info
            step = MigrationStep(
                sql=f"ALTER TABLE {change.table} ADD COLUMN {change.column} {change.new_value or 'TEXT'};",
                change_type=change.change_type,
                table=change.table,
                column=change.column,
                comment=f"Add column: {change.description}",
            )
            migration.add_step(step)

        # 9. Add tables
        for change in add_tables:
            if new_schema:
                table = new_schema.get_table(change.table)
                if table:
                    step = MigrationStep(
                        sql=self.dialect.render_create_table(change.table, table.columns),
                        change_type=change.change_type,
                        table=change.table,
                        comment=f"Create table: {change.description}",
                    )
                    migration.add_step(step)
                    continue
            # Fallback
            step = MigrationStep(
                sql=f"CREATE TABLE {change.table} ();",
                change_type=change.change_type,
                table=change.table,
                comment=f"Create table: {change.description}",
            )
            migration.add_step(step)

        # 10. Add foreign keys
        for change in add_fks:
            if new_schema:
                table = new_schema.get_table(change.table)
                if table and table.foreign_keys:
                    for fk in table.foreign_keys:
                        if change.new_value and fk.name in change.new_value:
                            step = MigrationStep(
                                sql=self.dialect.render_foreign_key(fk, change.table),
                                change_type=change.change_type,
                                table=change.table,
                                comment=f"Add FK: {change.description}",
                            )
                            migration.add_step(step)
                            break
            else:
                step = MigrationStep(
                    sql=f"-- Add foreign key: {change.description}",
                    change_type=change.change_type,
                    table=change.table,
                    comment=f"Add FK: {change.description}",
                )
                migration.add_step(step)

        # 11. Add indexes
        for change in add_indexes:
            if new_schema:
                table = new_schema.get_table(change.table)
                if table:
                    for idx in table.indexes:
                        if change.new_value and idx.name in change.new_value:
                            step = MigrationStep(
                                sql=self.dialect.render_index(idx),
                                change_type=change.change_type,
                                table=change.table,
                                comment=f"Add index: {change.description}",
                            )
                            migration.add_step(step)
                            break
            else:
                step = MigrationStep(
                    sql=f"-- Add index: {change.description}",
                    change_type=change.change_type,
                    table=change.table,
                    comment=f"Add index: {change.description}",
                )
                migration.add_step(step)

        # 12. Add unique constraints
        for change in add_unique_constraints:
            if new_schema:
                table = new_schema.get_table(change.table)
                if table:
                    for uc in table.unique_constraints:
                        step = MigrationStep(
                            sql=self.dialect.render_unique_constraint(uc),
                            change_type=change.change_type,
                            table=change.table,
                            comment=f"Add unique constraint: {change.description}",
                        )
                        migration.add_step(step)
                        break
            else:
                step = MigrationStep(
                    sql=f"-- Add unique constraint: {change.description}",
                    change_type=change.change_type,
                    table=change.table,
                    comment=f"Add unique constraint: {change.description}",
                )
                migration.add_step(step)

        # 13. Add check constraints
        for change in add_checks:
            if new_schema:
                table = new_schema.get_table(change.table)
                if table:
                    for chk in table.checks:
                        step = MigrationStep(
                            sql=self.dialect.render_check(chk),
                            change_type=change.change_type,
                            table=change.table,
                            comment=f"Add check constraint: {change.description}",
                        )
                        migration.add_step(step)
                        break
            else:
                step = MigrationStep(
                    sql=f"-- Add check constraint: {change.description}",
                    change_type=change.change_type,
                    table=change.table,
                    comment=f"Add check constraint: {change.description}",
                )
                migration.add_step(step)

        return migration

    def _generate_alter_column_steps(
        self, change, new_schema: Optional[Schema], migration: Migration
    ) -> None:
        """Generate ALTER COLUMN migration steps."""
        ct = change.change_type

        if ct == ChangeType.COLUMN_TYPE_CHANGED:
            if new_schema:
                table = new_schema.get_table(change.table)
                if table and change.column:
                    col = table.get_column(change.column)
                    if col:
                        step = MigrationStep(
                            sql=self.dialect.render_alter_column_type(change.table, col),
                            change_type=ct,
                            table=change.table,
                            column=change.column,
                            comment=f"Alter column type: {change.description}",
                        )
                        migration.add_step(step)
                        return
            step = MigrationStep(
                sql=f"ALTER TABLE {change.table} ALTER COLUMN {change.column} TYPE {change.new_value};",
                change_type=ct,
                table=change.table,
                column=change.column,
                comment=f"Alter column type: {change.description}",
            )
            migration.add_step(step)

        elif ct == ChangeType.COLUMN_NULLABILITY_CHANGED:
            nullable = change.new_value == "nullable"
            step = MigrationStep(
                sql=self.dialect.render_alter_column_nullability(
                    change.table, change.column or "unknown", nullable
                ),
                change_type=ct,
                table=change.table,
                column=change.column,
                comment=f"Alter nullability: {change.description}",
            )
            migration.add_step(step)

        elif ct == ChangeType.COLUMN_DEFAULT_CHANGED:
            step = MigrationStep(
                sql=self.dialect.render_alter_column_default(
                    change.table, change.column or "unknown", change.new_value
                ),
                change_type=ct,
                table=change.table,
                column=change.column,
                comment=f"Alter default: {change.description}",
            )
            migration.add_step(step)

        elif ct == ChangeType.COLUMN_PRIMARY_KEY_CHANGED:
            # Primary key changes require dropping and re-adding the constraint
            if change.new_value == "True":
                sql = f"ALTER TABLE {change.table} ADD PRIMARY KEY ({change.column});"
            else:
                sql = f"ALTER TABLE {change.table} DROP PRIMARY KEY;"
            step = MigrationStep(
                sql=sql,
                change_type=ct,
                table=change.table,
                column=change.column,
                comment=f"Alter primary key: {change.description}",
            )
            migration.add_step(step)

        elif ct == ChangeType.COLUMN_UNIQUE_CHANGED:
            if change.new_value == "True":
                sql = f"ALTER TABLE {change.table} ADD CONSTRAINT uq_{change.table}_{change.column} UNIQUE ({change.column});"
            else:
                sql = f"ALTER TABLE {change.table} DROP CONSTRAINT uq_{change.table}_{change.column};"
            step = MigrationStep(
                sql=sql,
                change_type=ct,
                table=change.table,
                column=change.column,
                comment=f"Alter unique: {change.description}",
            )
            migration.add_step(step)

        elif ct == ChangeType.COLUMN_FOREIGN_KEY_CHANGED:
            if change.new_value:
                ref = change.new_value
                sql = f"ALTER TABLE {change.table} ADD CONSTRAINT fk_{change.table}_{change.column} FOREIGN KEY ({change.column}) REFERENCES {ref};"
            else:
                sql = f"ALTER TABLE {change.table} DROP CONSTRAINT fk_{change.table}_{change.column};"
            step = MigrationStep(
                sql=sql,
                change_type=ct,
                table=change.table,
                column=change.column,
                comment=f"Alter foreign key: {change.description}",
            )
            migration.add_step(step)

        elif ct == ChangeType.COLUMN_AUTO_INCREMENT_CHANGED:
            # Auto increment changes typically require column redefinition
            step = MigrationStep(
                sql=f"-- Auto-increment change on {change.table}.{change.column}: {change.description}. May require column recreation.",
                change_type=ct,
                table=change.table,
                column=change.column,
                comment=f"Alter auto_increment: {change.description}",
            )
            migration.add_step(step)
