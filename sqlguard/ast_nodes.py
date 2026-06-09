"""SQL Abstract Syntax Tree nodes for SQLGuard.

Defines the data structures that represent a parsed SQL query as a tree.
Used by the parser to produce structured output and by analyzers to
perform semantic checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ─── Base ────────────────────────────────────────────────────────────────


class AstNode:
    """Base class for all AST nodes."""

    def accept(self, visitor: AstVisitor) -> None:
        """Accept a visitor (double-dispatch)."""
        method_name = f"visit_{type(self).__name__}"
        method = getattr(visitor, method_name, None)
        if method:
            method(self)


# ─── Expressions ─────────────────────────────────────────────────────────


class Expression(AstNode):
    """Base class for all SQL expressions."""


@dataclass
class Literal(Expression):
    """A literal value: integer, float, string, boolean, null."""

    value: str | int | float | None | bool
    kind: str = "string"  # "integer", "float", "string", "boolean", "null"

    def __repr__(self) -> str:
        return f"Literal({self.value!r})"


@dataclass
class ColumnRef(Expression):
    """A reference to a column, optionally qualified by table name."""

    name: str
    table: str | None = None
    schema: str | None = None

    @property
    def qualified_name(self) -> str:
        if self.table:
            return f"{self.table}.{self.name}"
        return self.name

    def __repr__(self) -> str:
        return f"ColumnRef({self.qualified_name})"


@dataclass
class Star(Expression):
    """A * or table.* reference."""

    table: str | None = None

    def __repr__(self) -> str:
        return f"Star({self.table or '*'})"


@dataclass
class BinaryOp(Expression):
    """A binary operation: left OP right (e.g., a + b, a = b)."""

    op: str
    left: Expression
    right: Expression

    def __repr__(self) -> str:
        return f"BinaryOp({self.left} {self.op} {self.right})"


@dataclass
class UnaryOp(Expression):
    """A unary operation: OP expr (e.g., -x, NOT x)."""

    op: str
    operand: Expression

    def __repr__(self) -> str:
        return f"UnaryOp({self.op} {self.operand})"


@dataclass
class FunctionCall(Expression):
    """A function call: name(args) with optional FILTER and OVER clauses."""

    name: str
    args: list[Expression] = field(default_factory=list)
    distinct: bool = False
    filter_clause: Expression | None = None
    over_clause: WindowSpec | None = None

    def __repr__(self) -> str:
        args_str = ", ".join(str(a) for a in self.args)
        return f"FunctionCall({self.name}({args_str}))"


@dataclass
class WindowSpec(AstNode):
    """A window specification (OVER ...)."""

    partition_by: list[Expression] = field(default_factory=list)
    order_by: list[SortItem] = field(default_factory=list)
    frame_clause: FrameClause | None = None

    def __repr__(self) -> str:
        return "WindowSpec(...)"


@dataclass
class FrameClause(AstNode):
    """A window frame clause (ROWS BETWEEN ... AND ...)."""

    mode: str  # "ROWS" or "RANGE"
    start: FrameBound
    end: FrameBound | None = None


@dataclass
class FrameBound(AstNode):
    """A window frame boundary."""

    kind: (
        str  # "UNBOUNDED_PRECEDING", "CURRENT_ROW", "PRECEDING", "FOLLOWING", "UNBOUNDED_FOLLOWING"
    )
    offset: Expression | None = None


@dataclass
class SortItem(AstNode):
    """An ORDER BY item with optional direction and nulls placement."""

    expr: Expression
    ascending: bool = True
    nulls_first: bool | None = None  # None means database default

    @property
    def direction(self) -> str:
        return "ASC" if self.ascending else "DESC"


@dataclass
class CaseExpression(Expression):
    """A CASE expression."""

    operand: Expression | None = None  # Simple CASE: CASE x WHEN ...
    when_clauses: list[WhenClause] = field(default_factory=list)
    else_clause: Expression | None = None


@dataclass
class WhenClause(AstNode):
    """A WHEN ... THEN ... clause in a CASE expression."""

    condition: Expression
    result: Expression


@dataclass
class InExpression(Expression):
    """An IN expression: expr IN (values) or expr IN (subquery)."""

    expr: Expression
    values: list[Expression] = field(default_factory=list)
    subquery: SelectStatement | None = None
    negated: bool = False


@dataclass
class BetweenExpression(Expression):
    """A BETWEEN expression: expr BETWEEN low AND high."""

    expr: Expression
    low: Expression
    high: Expression
    negated: bool = False


@dataclass
class LikeExpression(Expression):
    """A LIKE expression: expr LIKE pattern."""

    expr: Expression
    pattern: Expression
    escape: str | None = None
    negated: bool = False

    @property
    def has_leading_wildcard(self) -> bool:
        """Check if the pattern starts with a wildcard."""
        if isinstance(self.pattern, Literal) and isinstance(self.pattern.value, str):
            return self.pattern.value.startswith("%")
        return False


@dataclass
class IsNullExpression(Expression):
    """An IS NULL / IS NOT NULL expression."""

    expr: Expression
    negated: bool = False


@dataclass
class ExistsExpression(Expression):
    """An EXISTS (subquery) expression."""

    subquery: SelectStatement
    negated: bool = False


@dataclass
class SubqueryExpression(Expression):
    """A subquery used as an expression: (SELECT ...)."""

    subquery: SelectStatement


@dataclass
class CastExpression(Expression):
    """A CAST(expr AS type) expression."""

    expr: Expression
    target_type: str


@dataclass
class CollateExpression(Expression):
    """A expr COLLATE collation expression."""

    expr: Expression
    collation: str


@dataclass
class ArrayExpression(Expression):
    """An array constructor: ARRAY[1, 2, 3] or ARRAY(SELECT ...)."""

    elements: list[Expression] = field(default_factory=list)
    subquery: SelectStatement | None = None


@dataclass
class ArrayAccess(Expression):
    """An array element access: arr[index]."""

    array: Expression
    index: Expression


@dataclass
class TypeCast(Expression):
    """A PostgreSQL-style type cast: expr::type."""

    expr: Expression
    target_type: str


@dataclass
class ParameterRef(Expression):
    """A parameter reference: ?, $1, :name."""

    name: str
    index: int | None = None


# ─── Table references ────────────────────────────────────────────────────


@dataclass
class TableRef(AstNode):
    """A reference to a table."""

    name: str
    schema: str | None = None
    alias: str | None = None

    @property
    def qualified_name(self) -> str:
        if self.schema:
            return f"{self.schema}.{self.name}"
        return self.name

    def __repr__(self) -> str:
        if self.alias:
            return f"TableRef({self.qualified_name} AS {self.alias})"
        return f"TableRef({self.qualified_name})"


@dataclass
class SubqueryRef(AstNode):
    """A subquery used as a table source."""

    subquery: SelectStatement
    alias: str | None = None


@dataclass
class FunctionRef(AstNode):
    """A table-valued function used as a table source."""

    name: str
    args: list[Expression] = field(default_factory=list)
    alias: str | None = None
    lateral: bool = False


@dataclass
class JoinClause(AstNode):
    """A JOIN clause."""

    join_type: str  # "INNER", "LEFT", "RIGHT", "FULL", "CROSS"
    right: TableRef | SubqueryRef | FunctionRef
    condition: Expression | None = None  # ON condition
    using_columns: list[str] = field(default_factory=list)  # USING columns
    natural: bool = False

    @property
    def is_cross_join(self) -> bool:
        return self.join_type == "CROSS" and self.condition is None

    @property
    def has_condition(self) -> bool:
        return self.condition is not None or bool(self.using_columns) or self.natural


# ─── Statements ──────────────────────────────────────────────────────────


@dataclass
class SelectStatement(AstNode):
    """A SELECT statement."""

    distinct: bool = False
    columns: list[Expression | SelectColumn] = field(default_factory=list)
    from_clause: FromClause | None = None
    where_clause: Expression | None = None
    group_by: list[Expression] = field(default_factory=list)
    having: Expression | None = None
    order_by: list[SortItem] = field(default_factory=list)
    limit: Expression | None = None
    offset: Expression | None = None
    cte_list: list[CommonTableExpression] = field(default_factory=list)
    union_clauses: list[SetOperation] = field(default_factory=list)
    for_update: bool = False
    for_update_tables: list[str] = field(default_factory=list)
    nowait: bool = False

    @property
    def is_compound(self) -> bool:
        """Whether this is a compound query (UNION, INTERSECT, EXCEPT)."""
        return bool(self.union_clauses)

    def get_all_tables(self) -> list[TableRef]:
        """Collect all table references from the FROM clause and JOINs."""
        tables: list[TableRef] = []
        if self.from_clause:
            tables.extend(self.from_clause.get_all_tables())
        return tables

    def get_all_columns(self) -> list[ColumnRef]:
        """Collect all column references from the SELECT list."""
        columns: list[ColumnRef] = []
        for col in self.columns:
            if isinstance(col, SelectColumn):
                _collect_columns(col.expr, columns)
            elif isinstance(col, ColumnRef):
                columns.append(col)
        return columns


@dataclass
class SelectColumn(AstNode):
    """A column in a SELECT list with optional alias."""

    expr: Expression
    alias: str | None = None


@dataclass
class FromClause(AstNode):
    """A FROM clause with a primary table and optional JOINs."""

    source: TableRef | SubqueryRef | FunctionRef
    joins: list[JoinClause] = field(default_factory=list)

    def get_all_tables(self) -> list[TableRef]:
        """Collect all table references."""
        tables: list[TableRef] = []
        if isinstance(self.source, TableRef):
            tables.append(self.source)
        for join in self.joins:
            if isinstance(join.right, TableRef):
                tables.append(join.right)
        return tables

    @property
    def has_joins(self) -> bool:
        return bool(self.joins)

    @property
    def join_count(self) -> int:
        return len(self.joins)


@dataclass
class InsertStatement(AstNode):
    """An INSERT statement."""

    table: TableRef
    columns: list[str] = field(default_factory=list)
    values: list[list[Expression]] = field(default_factory=list)
    subquery: SelectStatement | None = None
    on_conflict: OnConflictClause | None = None
    returning: list[Expression] = field(default_factory=list)


@dataclass
class UpdateStatement(AstNode):
    """An UPDATE statement."""

    table: TableRef
    assignments: list[Assignment] = field(default_factory=list)
    from_clause: FromClause | None = None
    where_clause: Expression | None = None
    returning: list[Expression] = field(default_factory=list)


@dataclass
class DeleteStatement(AstNode):
    """A DELETE statement."""

    table: TableRef
    using_clause: FromClause | None = None
    where_clause: Expression | None = None
    returning: list[Expression] = field(default_factory=list)


@dataclass
class Assignment(AstNode):
    """An assignment in an UPDATE SET clause: column = expression."""

    column: str
    value: Expression


@dataclass
class OnConflictClause(AstNode):
    """An ON CONFLICT clause for INSERT statements."""

    target: Expression | None = None  # ON CONFLICT (columns) or ON CONSTRAINT name
    action: str = "NOTHING"  # "NOTHING" or "UPDATE"
    update_assignments: list[Assignment] = field(default_factory=list)
    where_clause: Expression | None = None


# ─── DDL statements ──────────────────────────────────────────────────────


@dataclass
class CreateTableStatement(AstNode):
    """A CREATE TABLE statement."""

    name: str
    schema: str | None = None
    if_not_exists: bool = False
    temporary: bool = False
    columns: list[ColumnDefinition] = field(default_factory=list)
    table_constraints: list[TableConstraint] = field(default_factory=list)
    inherits: str | None = None


@dataclass
class ColumnDefinition(AstNode):
    """A column definition in CREATE TABLE."""

    name: str
    data_type: str
    type_params: str | None = None
    not_null: bool = False
    default: Expression | None = None
    primary_key: bool = False
    unique: bool = False
    references: str | None = None
    check: Expression | None = None
    auto_increment: bool = False
    identity: str | None = None  # GENERATED ALWAYS/LAST AS IDENTITY


@dataclass
class TableConstraint(AstNode):
    """A table-level constraint in CREATE TABLE."""

    name: str | None = None
    constraint_type: str = ""  # "PRIMARY_KEY", "UNIQUE", "FOREIGN_KEY", "CHECK"
    columns: list[str] = field(default_factory=list)
    reference_table: str | None = None
    reference_columns: list[str] = field(default_factory=list)
    on_delete: str | None = None
    on_update: str | None = None
    check_expression: Expression | None = None
    deferrable: bool = False
    initially_deferred: bool = False


@dataclass
class CreateIndexStatement(AstNode):
    """A CREATE INDEX statement."""

    name: str
    table: str
    columns: list[Expression] = field(default_factory=list)
    unique: bool = False
    if_not_exists: bool = False
    where_clause: Expression | None = None
    method: str | None = None


@dataclass
class DropTableStatement(AstNode):
    """A DROP TABLE statement."""

    name: str
    schema: str | None = None
    if_exists: bool = False
    cascade: bool = False


@dataclass
class AlterTableStatement(AstNode):
    """An ALTER TABLE statement."""

    name: str
    actions: list[AlterAction] = field(default_factory=list)


@dataclass
class AlterAction(AstNode):
    """A single action in an ALTER TABLE statement."""

    action_type: str  # "ADD_COLUMN", "DROP_COLUMN", "ALTER_COLUMN", "ADD_CONSTRAINT", etc.
    column_name: str | None = None
    column_def: ColumnDefinition | None = None
    constraint: TableConstraint | None = None
    data_type: str | None = None
    default_value: Expression | None = None
    nullable: bool | None = None
    new_name: str | None = None  # For RENAME


# ─── Other AST nodes ─────────────────────────────────────────────────────


@dataclass
class CommonTableExpression(AstNode):
    """A common table expression (WITH ... AS ...)."""

    name: str
    subquery: SelectStatement
    columns: list[str] = field(default_factory=list)
    recursive: bool = False


@dataclass
class SetOperation(AstNode):
    """A set operation (UNION, INTERSECT, EXCEPT)."""

    operation: str  # "UNION", "INTERSECT", "EXCEPT"
    right: SelectStatement
    all: bool = False


# ─── Top-level ───────────────────────────────────────────────────────────


@dataclass
class SqlProgram(AstNode):
    """A complete SQL program (one or more statements separated by semicolons)."""

    statements: list[
        SelectStatement
        | InsertStatement
        | UpdateStatement
        | DeleteStatement
        | CreateTableStatement
        | CreateIndexStatement
        | DropTableStatement
        | AlterTableStatement
    ] = field(default_factory=list)


# ─── Helpers ─────────────────────────────────────────────────────────────


def _collect_columns(expr: Expression, result: list[ColumnRef]) -> None:
    """Recursively collect ColumnRef nodes from an expression."""
    if isinstance(expr, ColumnRef):
        result.append(expr)
    elif isinstance(expr, BinaryOp):
        _collect_columns(expr.left, result)
        _collect_columns(expr.right, result)
    elif isinstance(expr, UnaryOp):
        _collect_columns(expr.operand, result)
    elif isinstance(expr, FunctionCall):
        for arg in expr.args:
            _collect_columns(arg, result)
    elif isinstance(expr, CaseExpression):
        if expr.operand:
            _collect_columns(expr.operand, result)
        for when in expr.when_clauses:
            _collect_columns(when.condition, result)
            _collect_columns(when.result, result)
        if expr.else_clause:
            _collect_columns(expr.else_clause, result)
    elif isinstance(expr, InExpression):
        _collect_columns(expr.expr, result)
        for v in expr.values:
            _collect_columns(v, result)
    elif isinstance(expr, BetweenExpression):
        _collect_columns(expr.expr, result)
        _collect_columns(expr.low, result)
        _collect_columns(expr.high, result)
    elif isinstance(expr, LikeExpression):
        _collect_columns(expr.expr, result)
        _collect_columns(expr.pattern, result)
    elif isinstance(expr, (IsNullExpression, CastExpression, TypeCast, CollateExpression)):
        _collect_columns(expr.expr, result)
    elif isinstance(expr, ArrayAccess):
        _collect_columns(expr.array, result)
        _collect_columns(expr.index, result)


# ─── Visitor interface ───────────────────────────────────────────────────


class AstVisitor:
    """Base class for AST visitors. Subclass and override specific visit_* methods."""

    def visit_SelectStatement(self, node: SelectStatement) -> None:
        pass

    def visit_InsertStatement(self, node: InsertStatement) -> None:
        pass

    def visit_UpdateStatement(self, node: UpdateStatement) -> None:
        pass

    def visit_DeleteStatement(self, node: DeleteStatement) -> None:
        pass

    def visit_ColumnRef(self, node: ColumnRef) -> None:
        pass

    def visit_FunctionCall(self, node: FunctionCall) -> None:
        pass

    def visit_TableRef(self, node: TableRef) -> None:
        pass

    def visit_Literal(self, node: Literal) -> None:
        pass
