# 🛡️ SQLGuard

Schema validation, migration generation, and query safety for Python SQL projects.

## Features

- **Schema Definition**: Define database schemas in Python with full type support
- **Schema Diff**: Compare two schemas and detect breaking vs safe changes
- **Migration Generation**: Auto-generate ALTER TABLE migration scripts from schema diffs
- **SQL Linting**: Catch unsafe patterns (SELECT *, missing WHERE on DELETE/UPDATE, SQL injection risks)
- **Query Validation**: Validate queries against your schema (column existence, type compatibility)
- **CLI**: Full command-line interface for all operations
- **Multiple Dialects**: Support for PostgreSQL, MySQL, and SQLite column types

## Installation

```bash
pip install sqlguard
```

## Quick Start

### Define a Schema

```python
from sqlguard import Schema, Table, Column

schema = Schema("my_app", [
    Table("users", [
        Column("id", "integer", primary_key=True),
        Column("email", "varchar", nullable=False, unique=True),
        Column("name", "varchar", nullable=False),
        Column("created_at", "timestamp", default="now()"),
    ]),
    Table("posts", [
        Column("id", "integer", primary_key=True),
        Column("user_id", "integer", nullable=False, references="users.id"),
        Column("title", "varchar", nullable=False),
        Column("body", "text"),
        Column("published", "boolean", default="false"),
    ]),
])
```

### Diff Two Schemas

```python
from sqlguard import SchemaDiffer

differ = SchemaDiffer()
diff = differ.diff(old_schema, new_schema)

for change in diff.breaking_changes:
    print(f"⚠️  BREAKING: {change}")

for change in diff.safe_changes:
    print(f"✅ SAFE: {change}")
```

### Generate Migrations

```python
from sqlguard import MigrationGenerator

generator = MigrationGenerator(dialect="postgresql")
migrations = generator.generate(diff)

for migration in migrations:
    print(migration.to_sql())
```

### Lint SQL Queries

```python
from sqlguard import SQLLinter

linter = SQLLinter()
issues = linter.lint("SELECT * FROM users WHERE id = " + str(user_id))

for issue in issues:
    print(f"[{issue.severity}] {issue.rule}: {issue.message}")
```

### Validate Queries Against Schema

```python
from sqlguard import QueryValidator

validator = QueryValidator(schema)
errors = validator.validate("SELECT email, nam FROM users")

for error in errors:
    print(f"Invalid column: {error.column} in table: {error.table}")
```

### CLI

```bash
# Lint a SQL file
sqlguard lint queries.sql

# Diff two schema files
sqlguard diff old_schema.py new_schema.py

# Generate migration from diff
sqlguard migrate old_schema.py new_schema.py --dialect postgresql

# Validate queries against schema
sqlguard validate queries.sql --schema schema.py
```

## License

MIT
