"""Tests for sqlguard.parser module."""

import pytest

from sqlguard.ast_nodes import (
    AlterTableStatement,
    BetweenExpression,
    BinaryOp,
    CaseExpression,
    CastExpression,
    ColumnRef,
    CreateIndexStatement,
    CreateTableStatement,
    DeleteStatement,
    DropTableStatement,
    ExistsExpression,
    FunctionCall,
    InExpression,
    InsertStatement,
    IsNullExpression,
    LikeExpression,
    Literal,
    ParameterRef,
    SelectColumn,
    SelectStatement,
    Star,
    SubqueryExpression,
    SubqueryRef,
    TableRef,
    TypeCast,
    UnaryOp,
    UpdateStatement,
)
from sqlguard.parser import ParseError, parse_sql


class TestParserSelect:
    """Test SELECT statement parsing."""

    def test_simple_select(self):
        ast = parse_sql("SELECT 1")
        assert len(ast.statements) == 1
        stmt = ast.statements[0]
        assert isinstance(stmt, SelectStatement)
        assert len(stmt.columns) == 1

    def test_select_column_list(self):
        ast = parse_sql("SELECT id, name, email FROM users")
        stmt = ast.statements[0]
        assert isinstance(stmt, SelectStatement)
        assert len(stmt.columns) == 3

    def test_select_star(self):
        ast = parse_sql("SELECT * FROM users")
        stmt = ast.statements[0]
        assert isinstance(stmt, SelectStatement)
        assert len(stmt.columns) == 1
        assert isinstance(stmt.columns[0], SelectColumn)
        assert isinstance(stmt.columns[0].expr, Star)

    def test_select_distinct(self):
        ast = parse_sql("SELECT DISTINCT name FROM users")
        stmt = ast.statements[0]
        assert stmt.distinct is True

    def test_select_all(self):
        ast = parse_sql("SELECT ALL name FROM users")
        stmt = ast.statements[0]
        assert stmt.distinct is False

    def test_select_from_table(self):
        ast = parse_sql("SELECT id FROM users")
        stmt = ast.statements[0]
        assert stmt.from_clause is not None
        assert isinstance(stmt.from_clause.source, TableRef)
        assert stmt.from_clause.source.name == "users"

    def test_select_from_qualified_table(self):
        ast = parse_sql("SELECT id FROM public.users")
        stmt = ast.statements[0]
        assert stmt.from_clause.source.name == "users"
        assert stmt.from_clause.source.schema == "public"

    def test_select_with_alias(self):
        ast = parse_sql("SELECT id FROM users AS u")
        stmt = ast.statements[0]
        assert stmt.from_clause.source.alias == "u"

    def test_select_with_implicit_alias(self):
        ast = parse_sql("SELECT id FROM users u")
        stmt = ast.statements[0]
        assert stmt.from_clause.source.alias == "u"

    def test_select_where(self):
        ast = parse_sql("SELECT id FROM users WHERE id = 1")
        stmt = ast.statements[0]
        assert stmt.where_clause is not None
        assert isinstance(stmt.where_clause, BinaryOp)
        assert stmt.where_clause.op == "="

    def test_select_where_and(self):
        ast = parse_sql("SELECT id FROM users WHERE id = 1 AND name = 'test'")
        stmt = ast.statements[0]
        assert isinstance(stmt.where_clause, BinaryOp)
        assert stmt.where_clause.op == "AND"

    def test_select_where_or(self):
        ast = parse_sql("SELECT id FROM users WHERE id = 1 OR id = 2")
        stmt = ast.statements[0]
        assert isinstance(stmt.where_clause, BinaryOp)
        assert stmt.where_clause.op == "OR"

    def test_select_where_not(self):
        ast = parse_sql("SELECT id FROM users WHERE NOT active")
        stmt = ast.statements[0]
        assert isinstance(stmt.where_clause, UnaryOp)
        assert stmt.where_clause.op == "NOT"

    def test_select_group_by(self):
        ast = parse_sql("SELECT COUNT(*) FROM users GROUP BY status")
        stmt = ast.statements[0]
        assert len(stmt.group_by) == 1

    def test_select_having(self):
        ast = parse_sql("SELECT status, COUNT(*) FROM users GROUP BY status HAVING COUNT(*) > 5")
        stmt = ast.statements[0]
        assert stmt.having is not None

    def test_select_order_by(self):
        ast = parse_sql("SELECT id FROM users ORDER BY name ASC, id DESC")
        stmt = ast.statements[0]
        assert len(stmt.order_by) == 2
        assert stmt.order_by[0].ascending is True
        assert stmt.order_by[1].ascending is False

    def test_select_order_by_nulls(self):
        ast = parse_sql("SELECT id FROM users ORDER BY name ASC NULLS FIRST")
        stmt = ast.statements[0]
        assert stmt.order_by[0].nulls_first is True

    def test_select_limit(self):
        ast = parse_sql("SELECT id FROM users LIMIT 10")
        stmt = ast.statements[0]
        assert stmt.limit is not None

    def test_select_offset(self):
        ast = parse_sql("SELECT id FROM users LIMIT 10 OFFSET 20")
        stmt = ast.statements[0]
        assert stmt.offset is not None

    def test_select_for_update(self):
        ast = parse_sql("SELECT id FROM users WHERE id = 1 FOR UPDATE")
        stmt = ast.statements[0]
        assert stmt.for_update is True

    def test_select_for_update_nowait(self):
        ast = parse_sql("SELECT id FROM users WHERE id = 1 FOR UPDATE NOWAIT")
        stmt = ast.statements[0]
        assert stmt.for_update is True
        assert stmt.nowait is True


class TestParserSelectJoins:
    """Test JOIN parsing in SELECT statements."""

    def test_inner_join(self):
        ast = parse_sql("SELECT u.id FROM users u INNER JOIN orders o ON u.id = o.user_id")
        stmt = ast.statements[0]
        assert len(stmt.from_clause.joins) == 1
        assert stmt.from_clause.joins[0].join_type == "INNER"

    def test_left_join(self):
        ast = parse_sql("SELECT u.id FROM users u LEFT JOIN orders o ON u.id = o.user_id")
        stmt = ast.statements[0]
        assert stmt.from_clause.joins[0].join_type == "LEFT"

    def test_right_join(self):
        ast = parse_sql("SELECT u.id FROM users u RIGHT JOIN orders o ON u.id = o.user_id")
        stmt = ast.statements[0]
        assert stmt.from_clause.joins[0].join_type == "RIGHT"

    def test_full_outer_join(self):
        ast = parse_sql("SELECT u.id FROM users u FULL OUTER JOIN orders o ON u.id = o.user_id")
        stmt = ast.statements[0]
        assert stmt.from_clause.joins[0].join_type == "FULL"

    def test_cross_join(self):
        ast = parse_sql("SELECT u.id FROM users u CROSS JOIN orders o")
        stmt = ast.statements[0]
        assert stmt.from_clause.joins[0].join_type == "CROSS"

    def test_comma_join(self):
        ast = parse_sql("SELECT u.id FROM users u, orders o")
        stmt = ast.statements[0]
        assert len(stmt.from_clause.joins) == 1
        assert stmt.from_clause.joins[0].join_type == "CROSS"

    def test_multiple_joins(self):
        sql = """
        SELECT u.id, o.total, p.name
        FROM users u
        JOIN orders o ON u.id = o.user_id
        JOIN products p ON o.product_id = p.id
        """
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert len(stmt.from_clause.joins) == 2

    def test_join_using(self):
        ast = parse_sql("SELECT * FROM users u JOIN orders o USING (user_id)")
        stmt = ast.statements[0]
        assert stmt.from_clause.joins[0].using_columns == ["user_id"]

    def test_natural_join(self):
        ast = parse_sql("SELECT * FROM users NATURAL JOIN orders")
        stmt = ast.statements[0]
        assert stmt.from_clause.joins[0].natural is True


class TestParserSelectExpressions:
    """Test expression parsing in SELECT statements."""

    def test_column_ref(self):
        ast = parse_sql("SELECT name FROM users")
        col = ast.statements[0].columns[0]
        assert isinstance(col, SelectColumn)
        assert isinstance(col.expr, ColumnRef)
        assert col.expr.name == "name"

    def test_qualified_column_ref(self):
        ast = parse_sql("SELECT u.name FROM users u")
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, ColumnRef)
        assert col.expr.table == "u"
        assert col.expr.name == "name"

    def test_integer_literal(self):
        ast = parse_sql("SELECT 42")
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, Literal)
        assert col.expr.value == 42
        assert col.expr.kind == "integer"

    def test_float_literal(self):
        ast = parse_sql("SELECT 3.14")
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, Literal)
        assert col.expr.value == 3.14

    def test_string_literal(self):
        ast = parse_sql("SELECT 'hello'")
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, Literal)
        assert col.expr.value == "hello"
        assert col.expr.kind == "string"

    def test_null_literal(self):
        ast = parse_sql("SELECT NULL")
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, Literal)
        assert col.expr.value is None
        assert col.expr.kind == "null"

    def test_true_literal(self):
        ast = parse_sql("SELECT TRUE")
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, Literal)
        assert col.expr.value is True

    def test_false_literal(self):
        ast = parse_sql("SELECT FALSE")
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, Literal)
        assert col.expr.value is False

    def test_binary_addition(self):
        ast = parse_sql("SELECT price + tax")
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, BinaryOp)
        assert col.expr.op == "+"

    def test_binary_multiplication(self):
        ast = parse_sql("SELECT price * quantity")
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, BinaryOp)
        assert col.expr.op == "*"

    def test_unary_minus(self):
        ast = parse_sql("SELECT -price")
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, UnaryOp)
        assert col.expr.op == "-"

    def test_concatenation(self):
        ast = parse_sql("SELECT first_name || ' ' || last_name")
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, BinaryOp)
        assert col.expr.op == "||"

    def test_parenthesized_expression(self):
        ast = parse_sql("SELECT (price + tax) * quantity")
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, BinaryOp)
        assert col.expr.op == "*"

    def test_comparison_in_where(self):
        ast = parse_sql("SELECT id FROM users WHERE id > 5")
        where = ast.statements[0].where_clause
        assert isinstance(where, BinaryOp)
        assert where.op == ">"

    def test_is_null(self):
        ast = parse_sql("SELECT id FROM users WHERE name IS NULL")
        where = ast.statements[0].where_clause
        assert isinstance(where, IsNullExpression)
        assert where.negated is False

    def test_is_not_null(self):
        ast = parse_sql("SELECT id FROM users WHERE name IS NOT NULL")
        where = ast.statements[0].where_clause
        assert isinstance(where, IsNullExpression)
        assert where.negated is True

    def test_in_list(self):
        ast = parse_sql("SELECT id FROM users WHERE status IN ('active', 'pending')")
        where = ast.statements[0].where_clause
        assert isinstance(where, InExpression)
        assert len(where.values) == 2
        assert where.negated is False

    def test_not_in_list(self):
        ast = parse_sql("SELECT id FROM users WHERE status NOT IN ('inactive')")
        where = ast.statements[0].where_clause
        assert isinstance(where, InExpression)
        assert where.negated is True

    def test_between(self):
        ast = parse_sql("SELECT id FROM users WHERE age BETWEEN 18 AND 65")
        where = ast.statements[0].where_clause
        assert isinstance(where, BetweenExpression)
        assert where.negated is False

    def test_not_between(self):
        ast = parse_sql("SELECT id FROM users WHERE age NOT BETWEEN 18 AND 65")
        where = ast.statements[0].where_clause
        assert isinstance(where, BetweenExpression)
        assert where.negated is True

    def test_like(self):
        ast = parse_sql("SELECT id FROM users WHERE name LIKE 'John%'")
        where = ast.statements[0].where_clause
        assert isinstance(where, LikeExpression)

    def test_parameter_ref(self):
        ast = parse_sql("SELECT id FROM users WHERE id = $1")
        where = ast.statements[0].where_clause
        assert isinstance(where, BinaryOp)
        assert isinstance(where.right, ParameterRef)
        assert where.right.index == 1


class TestParserSelectFunctions:
    """Test function call parsing."""

    def test_count_star(self):
        ast = parse_sql("SELECT COUNT(*) FROM users")
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, FunctionCall)
        assert col.expr.name == "COUNT"
        assert len(col.expr.args) == 1

    def test_count_distinct(self):
        ast = parse_sql("SELECT COUNT(DISTINCT name) FROM users")
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, FunctionCall)
        assert col.expr.distinct is True

    def test_function_with_args(self):
        ast = parse_sql("SELECT COALESCE(name, 'unknown') FROM users")
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, FunctionCall)
        assert col.expr.name == "COALESCE"
        assert len(col.expr.args) == 2

    def test_nested_functions(self):
        ast = parse_sql("SELECT UPPER(TRIM(name)) FROM users")
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, FunctionCall)
        assert col.expr.name == "UPPER"
        assert isinstance(col.expr.args[0], FunctionCall)
        assert col.expr.args[0].name == "TRIM"

    def test_cast_expression(self):
        ast = parse_sql("SELECT CAST(id AS VARCHAR)")
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, CastExpression)
        assert col.expr.target_type == "VARCHAR"

    def test_double_colon_cast(self):
        ast = parse_sql("SELECT id::VARCHAR")
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, TypeCast)
        assert col.expr.target_type == "VARCHAR"

    def test_window_function(self):
        sql = "SELECT ROW_NUMBER() OVER (PARTITION BY dept ORDER BY salary DESC) FROM employees"
        ast = parse_sql(sql)
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, FunctionCall)
        assert col.expr.over_clause is not None
        assert len(col.expr.over_clause.partition_by) == 1
        assert len(col.expr.over_clause.order_by) == 1

    def test_window_function_with_frame(self):
        sql = "SELECT SUM(salary) OVER (ORDER BY hire_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) FROM employees"
        ast = parse_sql(sql)
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, FunctionCall)
        assert col.expr.over_clause is not None
        assert col.expr.over_clause.frame_clause is not None

    def test_case_expression(self):
        sql = "SELECT CASE WHEN status = 'active' THEN 1 ELSE 0 END FROM users"
        ast = parse_sql(sql)
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, CaseExpression)
        assert len(col.expr.when_clauses) == 1
        assert col.expr.else_clause is not None

    def test_simple_case(self):
        sql = (
            "SELECT CASE status WHEN 'active' THEN 1 WHEN 'inactive' THEN 0 ELSE -1 END FROM users"
        )
        ast = parse_sql(sql)
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, CaseExpression)
        assert col.expr.operand is not None
        assert len(col.expr.when_clauses) == 2

    def test_exists_subquery(self):
        sql = "SELECT id FROM users WHERE EXISTS (SELECT 1 FROM orders WHERE user_id = users.id)"
        ast = parse_sql(sql)
        where = ast.statements[0].where_clause
        assert isinstance(where, ExistsExpression)

    def test_in_subquery(self):
        sql = "SELECT id FROM users WHERE id IN (SELECT user_id FROM orders)"
        ast = parse_sql(sql)
        where = ast.statements[0].where_clause
        assert isinstance(where, InExpression)
        assert where.subquery is not None

    def test_subquery_expression(self):
        sql = "SELECT (SELECT MAX(id) FROM orders) AS max_order"
        ast = parse_sql(sql)
        col = ast.statements[0].columns[0]
        assert isinstance(col.expr, SubqueryExpression)


class TestParserSelectCTE:
    """Test CTE (WITH clause) parsing."""

    def test_simple_cte(self):
        sql = "WITH active_users AS (SELECT id FROM users WHERE active = TRUE) SELECT * FROM active_users"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert len(stmt.cte_list) == 1
        assert stmt.cte_list[0].name == "active_users"

    def test_recursive_cte(self):
        sql = """
        WITH RECURSIVE tree AS (
            SELECT id, parent_id FROM categories WHERE parent_id IS NULL
            UNION ALL
            SELECT c.id, c.parent_id FROM categories c JOIN tree t ON c.parent_id = t.id
        )
        SELECT * FROM tree
        """
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert stmt.cte_list[0].recursive is True

    def test_multiple_ctes(self):
        sql = """
        WITH
            users_cte AS (SELECT id FROM users),
            orders_cte AS (SELECT id FROM orders)
        SELECT * FROM users_cte JOIN orders_cte ON users_cte.id = orders_cte.id
        """
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert len(stmt.cte_list) == 2


class TestParserSelectSetOps:
    """Test set operations (UNION, INTERSECT, EXCEPT)."""

    def test_union(self):
        sql = "SELECT id FROM users UNION SELECT id FROM admins"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert len(stmt.union_clauses) == 1
        assert stmt.union_clauses[0].operation == "UNION"

    def test_union_all(self):
        sql = "SELECT id FROM users UNION ALL SELECT id FROM admins"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert stmt.union_clauses[0].all is True

    def test_intersect(self):
        sql = "SELECT id FROM users INTERSECT SELECT id FROM admins"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert stmt.union_clauses[0].operation == "INTERSECT"

    def test_except(self):
        sql = "SELECT id FROM users EXCEPT SELECT id FROM admins"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert stmt.union_clauses[0].operation == "EXCEPT"


class TestParserSelectColumnAlias:
    """Test column aliasing."""

    def test_explicit_alias(self):
        ast = parse_sql("SELECT id AS user_id FROM users")
        col = ast.statements[0].columns[0]
        assert col.alias == "user_id"

    def test_implicit_alias(self):
        ast = parse_sql("SELECT id user_id FROM users")
        col = ast.statements[0].columns[0]
        assert col.alias == "user_id"


class TestParserInsert:
    """Test INSERT statement parsing."""

    def test_simple_insert(self):
        sql = "INSERT INTO users (name, email) VALUES ('John', 'john@example.com')"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert isinstance(stmt, InsertStatement)
        assert stmt.table.name == "users"
        assert stmt.columns == ["name", "email"]
        assert len(stmt.values) == 1
        assert len(stmt.values[0]) == 2

    def test_insert_multiple_rows(self):
        sql = "INSERT INTO users (name) VALUES ('John'), ('Jane')"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert len(stmt.values) == 2

    def test_insert_on_conflict_nothing(self):
        sql = "INSERT INTO users (id, name) VALUES (1, 'John') ON CONFLICT (id) DO NOTHING"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert stmt.on_conflict is not None
        assert stmt.on_conflict.action == "NOTHING"

    def test_insert_on_conflict_update(self):
        sql = "INSERT INTO users (id, name) VALUES (1, 'John') ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert stmt.on_conflict is not None
        assert stmt.on_conflict.action == "UPDATE"

    def test_insert_returning(self):
        sql = "INSERT INTO users (name) VALUES ('John') RETURNING id"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert len(stmt.returning) == 1


class TestParserUpdate:
    """Test UPDATE statement parsing."""

    def test_simple_update(self):
        sql = "UPDATE users SET name = 'Jane' WHERE id = 1"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert isinstance(stmt, UpdateStatement)
        assert stmt.table.name == "users"
        assert len(stmt.assignments) == 1
        assert stmt.assignments[0].column == "name"
        assert stmt.where_clause is not None

    def test_update_multiple_columns(self):
        sql = "UPDATE users SET name = 'Jane', email = 'jane@example.com' WHERE id = 1"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert len(stmt.assignments) == 2

    def test_update_returning(self):
        sql = "UPDATE users SET name = 'Jane' WHERE id = 1 RETURNING id, name"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert len(stmt.returning) == 2


class TestParserDelete:
    """Test DELETE statement parsing."""

    def test_simple_delete(self):
        sql = "DELETE FROM users WHERE id = 1"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert isinstance(stmt, DeleteStatement)
        assert stmt.table.name == "users"
        assert stmt.where_clause is not None

    def test_delete_without_where(self):
        sql = "DELETE FROM users"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert isinstance(stmt, DeleteStatement)
        assert stmt.where_clause is None

    def test_delete_returning(self):
        sql = "DELETE FROM users WHERE id = 1 RETURNING id"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert len(stmt.returning) == 1


class TestParserDDL:
    """Test DDL statement parsing."""

    def test_create_table(self):
        sql = """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) UNIQUE,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert isinstance(stmt, CreateTableStatement)
        assert stmt.name == "users"
        assert len(stmt.columns) == 4

    def test_create_table_if_not_exists(self):
        sql = "CREATE TABLE IF NOT EXISTS users (id INTEGER)"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert stmt.if_not_exists is True

    def test_create_table_temporary(self):
        sql = "CREATE TEMPORARY TABLE session_data (id INTEGER)"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert stmt.temporary is True

    def test_create_table_with_constraints(self):
        sql = """
        CREATE TABLE orders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            total DECIMAL(10, 2),
            CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert len(stmt.columns) == 3
        assert len(stmt.table_constraints) == 1
        assert stmt.table_constraints[0].name == "fk_user"

    def test_create_index(self):
        sql = "CREATE INDEX idx_users_name ON users (name)"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert isinstance(stmt, CreateIndexStatement)
        assert stmt.name == "idx_users_name"
        assert stmt.table == "users"

    def test_create_unique_index(self):
        sql = "CREATE UNIQUE INDEX idx_users_email ON users (email)"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert stmt.unique is True

    def test_drop_table(self):
        sql = "DROP TABLE users"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert isinstance(stmt, DropTableStatement)
        assert stmt.name == "users"

    def test_drop_table_if_exists(self):
        sql = "DROP TABLE IF EXISTS users"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert stmt.if_exists is True

    def test_drop_table_cascade(self):
        sql = "DROP TABLE users CASCADE"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert stmt.cascade is True

    def test_alter_table_add_column(self):
        sql = "ALTER TABLE users ADD COLUMN age INTEGER"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert isinstance(stmt, AlterTableStatement)
        assert len(stmt.actions) == 1
        assert stmt.actions[0].action_type == "ADD_COLUMN"

    def test_alter_table_drop_column(self):
        sql = "ALTER TABLE users DROP COLUMN age"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert stmt.actions[0].action_type == "DROP_COLUMN"

    def test_alter_table_rename_column(self):
        sql = "ALTER TABLE users RENAME COLUMN name TO full_name"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert stmt.actions[0].action_type == "RENAME_COLUMN"
        assert stmt.actions[0].column_name == "name"
        assert stmt.actions[0].new_name == "full_name"


class TestParserMultipleStatements:
    """Test parsing multiple statements."""

    def test_two_selects(self):
        sql = "SELECT 1; SELECT 2"
        ast = parse_sql(sql)
        assert len(ast.statements) == 2

    def test_mixed_statements(self):
        sql = "CREATE TABLE users (id INTEGER); INSERT INTO users (id) VALUES (1); SELECT * FROM users"
        ast = parse_sql(sql)
        assert len(ast.statements) == 3


class TestParserErrors:
    """Test parse error handling."""

    def test_invalid_syntax(self):
        with pytest.raises(ParseError):
            parse_sql("SELECT 1 2")  # Unexpected token

    def test_unexpected_token(self):
        with pytest.raises(ParseError):
            parse_sql("INVALID SQL STATEMENT")


class TestParserComplexQueries:
    """Test parsing complex real-world queries."""

    def test_complex_join_query(self):
        sql = """
        SELECT
            u.id AS user_id,
            u.name,
            COUNT(o.id) AS order_count,
            SUM(o.total) AS total_spent
        FROM users u
        LEFT JOIN orders o ON u.id = o.user_id
        WHERE u.active = TRUE
        GROUP BY u.id, u.name
        HAVING COUNT(o.id) > 0
        ORDER BY total_spent DESC
        LIMIT 10
        """
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert isinstance(stmt, SelectStatement)
        assert stmt.from_clause is not None
        assert len(stmt.from_clause.joins) == 1
        assert stmt.from_clause.joins[0].join_type == "LEFT"
        assert stmt.distinct is False
        assert stmt.having is not None
        assert len(stmt.order_by) == 1
        assert stmt.limit is not None

    def test_nested_subquery(self):
        sql = """
        SELECT * FROM (
            SELECT id, name FROM users WHERE active = TRUE
        ) AS active_users
        """
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert isinstance(stmt.from_clause.source, SubqueryRef)
        assert stmt.from_clause.source.alias == "active_users"

    def test_window_function_complex(self):
        sql = """
        SELECT
            name,
            salary,
            RANK() OVER (PARTITION BY dept ORDER BY salary DESC),
            SUM(salary) OVER (PARTITION BY dept ORDER BY hire_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        FROM employees
        """
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert len(stmt.columns) == 4

    # def test_insert_from_select(self):
    #     sql = (
    #         "INSERT INTO archived_users (id, name) SELECT id, name FROM users WHERE active = FALSE"
    #     )
    #     ast = parse_sql(sql)
    #     stmt = ast.statements[0]
    #     assert isinstance(stmt, InsertStatement)
    #     assert stmt.subquery is not None

    def test_update_with_from(self):
        sql = "UPDATE users SET name = u2.name FROM users_backup u2 WHERE users.id = u2.id"
        ast = parse_sql(sql)
        stmt = ast.statements[0]
        assert isinstance(stmt, UpdateStatement)
        assert stmt.from_clause is not None
