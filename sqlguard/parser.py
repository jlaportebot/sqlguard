"""SQL recursive-descent parser for SQLGuard.

Parses a token stream (from sqlguard.tokens) into an AST
(from sqlguard.ast_nodes). Supports SELECT, INSERT, UPDATE, DELETE,
and basic DDL statements (CREATE TABLE, CREATE INDEX, DROP TABLE, ALTER TABLE).
"""

from __future__ import annotations

from sqlguard.ast_nodes import (
    AlterAction,
    AlterTableStatement,
    ArrayAccess,
    ArrayExpression,
    Assignment,
    BetweenExpression,
    BinaryOp,
    CaseExpression,
    CastExpression,
    CollateExpression,
    ColumnDefinition,
    ColumnRef,
    CommonTableExpression,
    CreateIndexStatement,
    CreateTableStatement,
    DeleteStatement,
    DropTableStatement,
    ExistsExpression,
    Expression,
    FrameBound,
    FrameClause,
    FromClause,
    FunctionCall,
    FunctionRef,
    InExpression,
    InsertStatement,
    IsNullExpression,
    JoinClause,
    LikeExpression,
    Literal,
    OnConflictClause,
    ParameterRef,
    SelectColumn,
    SelectStatement,
    SetOperation,
    SortItem,
    SqlProgram,
    Star,
    SubqueryExpression,
    SubqueryRef,
    TableConstraint,
    TableRef,
    TypeCast,
    UnaryOp,
    UpdateStatement,
    WhenClause,
    WindowSpec,
)
from sqlguard.tokens import Token, Tokenizer, TokenType


class ParseError(Exception):
    """Error raised when the parser encounters invalid SQL."""

    def __init__(self, message: str, token: Token | None = None) -> None:
        self.token = token
        loc = ""
        if token:
            loc = f" at line {token.line}, column {token.column}"
        super().__init__(f"Parse error{loc}: {message}")


class Parser:
    """Recursive-descent SQL parser.

    Usage:
        parser = Parser("SELECT * FROM users WHERE id = 1")
        ast = parser.parse()
    """

    def __init__(self, sql: str) -> None:
        self.tokens = Tokenizer(sql).tokenize()
        self.pos = 0

    # ─── Token navigation ────────────────────────────────────────────

    def _current(self) -> Token:
        """Get the current token."""
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return self.tokens[-1]  # EOF

    def _peek(self, offset: int = 1) -> Token:
        """Look ahead at a token."""
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return self.tokens[-1]

    def _advance(self) -> Token:
        """Consume and return the current token."""
        token = self._current()
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return token

    def _expect(self, type_: TokenType, value: str | None = None) -> Token:
        """Consume a token, raising ParseError if it doesn't match."""
        token = self._current()
        if token.type != type_:
            raise ParseError(
                f"Expected {type_.name}, got {token.type.name} ({token.value!r})",
                token,
            )
        if value is not None and token.value.upper() != value.upper():
            raise ParseError(
                f"Expected {value!r}, got {token.value!r}",
                token,
            )
        return self._advance()

    def _expect_keyword(self, keyword: str) -> Token:
        """Consume a keyword token."""
        token = self._current()
        if not token.keyword_is(keyword):
            raise ParseError(
                f"Expected keyword '{keyword}', got {token.value!r}",
                token,
            )
        return self._advance()

    def _match_keyword(self, keyword: str) -> bool:
        """Check if current token is a specific keyword."""
        return self._current().keyword_is(keyword)

    def _match_keywords(self, *keywords: str) -> bool:
        """Check if current token is one of several keywords."""
        return self._current().type == TokenType.KEYWORD and self._current().value in keywords

    def _consume_keyword(self, keyword: str) -> bool:
        """If current token is the keyword, consume it and return True."""
        if self._match_keyword(keyword):
            self._advance()
            return True
        return False

    def _match_type(self, type_: TokenType) -> bool:
        """Check if current token has the given type."""
        return self._current().type == type_

    def _match_punctuation(self, value: str) -> bool:
        """Check if current token is a specific punctuation."""
        t = self._current()
        if value == "(":
            return t.type == TokenType.LPAREN
        if value == ")":
            return t.type == TokenType.RPAREN
        if value == ",":
            return t.type == TokenType.COMMA
        if value == ";":
            return t.type == TokenType.SEMICOLON
        if value == ".":
            return t.type == TokenType.DOT
        if value == "::":
            return t.type == TokenType.COLON and t.value == "::"
        if value == ":":
            return t.type == TokenType.COLON and t.value == ":"
        return False

    # ─── Top-level parse ──────────────────────────────────────────────

    def parse(self) -> SqlProgram:
        """Parse the SQL string into a SqlProgram AST."""
        statements: list = []

        while not self._match_type(TokenType.EOF):
            # Skip semicolons between statements
            if self._match_punctuation(";"):
                self._advance()
                continue

            stmt = self._parse_statement()
            if stmt is not None:
                statements.append(stmt)

            # Consume optional trailing semicolon
            if self._match_punctuation(";"):
                self._advance()

        return SqlProgram(statements=statements)

    def _parse_statement(self):
        """Parse a single SQL statement."""
        token = self._current()

        if token.type == TokenType.KEYWORD:
            kw = token.value
            if kw in ("SELECT", "WITH"):
                return self._parse_select()
            elif kw == "INSERT":
                return self._parse_insert()
            elif kw == "UPDATE":
                return self._parse_update()
            elif kw == "DELETE":
                return self._parse_delete()
            elif kw == "CREATE":
                return self._parse_create()
            elif kw == "DROP":
                return self._parse_drop()
            elif kw == "ALTER":
                return self._parse_alter()
            elif kw in ("EXPLAIN", "ANALYZE"):
                # EXPLAIN / ANALYZE: skip the keyword and parse the inner statement
                self._advance()
                if self._match_keyword("ANALYZE"):
                    self._advance()
                return self._parse_statement()
            elif kw == "TRUNCATE":
                return self._parse_truncate()

        raise ParseError(f"Unexpected token: {token.value!r}", token)

    # ─── SELECT ───────────────────────────────────────────────────────

    def _parse_select(self) -> SelectStatement:
        """Parse a SELECT statement (including CTEs)."""
        cte_list: list[CommonTableExpression] = []

        # WITH clause
        if self._match_keyword("WITH"):
            cte_list = self._parse_with_clause()

        self._expect_keyword("SELECT")

        stmt = SelectStatement(cte_list=cte_list)

        # DISTINCT / ALL
        if self._consume_keyword("DISTINCT"):
            stmt.distinct = True
        elif self._consume_keyword("ALL"):
            stmt.distinct = False

        # TOP N (SQL Server style)
        if self._consume_keyword("TOP"):
            top_token = self._expect(TokenType.INTEGER)
            _ = int(top_token.value)

        # SELECT list
        stmt.columns = self._parse_select_list()

        # FROM clause
        if self._match_keyword("FROM"):
            self._advance()
            stmt.from_clause = self._parse_from_clause()

        # WHERE clause
        if self._consume_keyword("WHERE"):
            stmt.where_clause = self._parse_expression()

        # GROUP BY
        if self._match_keyword("GROUP"):
            self._advance()
            self._expect_keyword("BY")
            stmt.group_by = self._parse_expression_list()

        # HAVING
        if self._consume_keyword("HAVING"):
            stmt.having = self._parse_expression()

        # UNION / INTERSECT / EXCEPT
        while self._match_keywords("UNION", "INTERSECT", "EXCEPT"):
            op = self._advance().value
            all_ = self._consume_keyword("ALL")
            right = self._parse_select_body()
            stmt.union_clauses.append(SetOperation(operation=op, right=right, all=all_))

        # ORDER BY
        if self._match_keyword("ORDER"):
            self._advance()
            self._expect_keyword("BY")
            stmt.order_by = self._parse_order_by_list()

        # LIMIT
        if self._consume_keyword("LIMIT"):
            stmt.limit = self._parse_expression()

        # OFFSET
        if self._consume_keyword("OFFSET"):
            stmt.offset = self._parse_expression()

        # FOR UPDATE
        if self._match_keyword("FOR"):
            self._advance()
            if self._consume_keyword("UPDATE"):
                stmt.for_update = True
                # Optional: OF table_name
                if self._consume_keyword("OF"):
                    while True:
                        name = self._parse_identifier()
                        stmt.for_update_tables.append(name)
                        if not self._match_punctuation(","):
                            break
                        self._advance()
                if self._consume_keyword("NOWAIT"):
                    stmt.nowait = True
                elif self._consume_keyword("SKIP"):
                    self._expect_keyword("LOCKED")

        return stmt

    def _parse_select_body(self) -> SelectStatement:
        """Parse the body of a SELECT (without CTEs) — used for set operations."""
        self._expect_keyword("SELECT")
        stmt = SelectStatement()

        if self._consume_keyword("DISTINCT"):
            stmt.distinct = True
        elif self._consume_keyword("ALL"):
            stmt.distinct = False

        stmt.columns = self._parse_select_list()

        if self._match_keyword("FROM"):
            self._advance()
            stmt.from_clause = self._parse_from_clause()

        if self._consume_keyword("WHERE"):
            stmt.where_clause = self._parse_expression()

        if self._match_keyword("GROUP"):
            self._advance()
            self._expect_keyword("BY")
            stmt.group_by = self._parse_expression_list()

        if self._consume_keyword("HAVING"):
            stmt.having = self._parse_expression()

        return stmt

    def _parse_with_clause(self) -> list[CommonTableExpression]:
        """Parse a WITH clause (common table expressions)."""
        self._expect_keyword("WITH")
        recursive = self._consume_keyword("RECURSIVE")
        ctes: list[CommonTableExpression] = []

        while True:
            name = self._parse_identifier()
            columns: list[str] = []

            # Optional column list: (col1, col2)
            if self._match_punctuation("("):
                self._advance()
                columns = self._parse_identifier_list()
                self._expect_punctuation(")")

            self._expect_keyword("AS")
            self._expect_punctuation("(")
            subquery = self._parse_select()
            self._expect_punctuation(")")

            ctes.append(
                CommonTableExpression(
                    name=name,
                    subquery=subquery,
                    columns=columns,
                    recursive=recursive,
                )
            )

            if not self._match_punctuation(","):
                break
            self._advance()

        return ctes

    def _parse_select_list(self) -> list:
        """Parse the SELECT column list."""
        columns: list = []

        while True:
            if self._match_type(TokenType.STAR):
                self._advance()
                # Check for table.* pattern
                if self._match_punctuation("."):
                    self._advance()
                    if self._match_type(TokenType.STAR):
                        # This is actually handled differently — backtrack not easy
                        # Instead we handle table.* in the column ref parsing
                        self._advance()
                        columns.append(SelectColumn(expr=Star(table=None)))
                    else:
                        # This shouldn't happen after table., but handle gracefully
                        pass
                else:
                    columns.append(SelectColumn(expr=Star()))
            else:
                expr = self._parse_expression()
                alias = None
                if self._consume_keyword("AS"):
                    alias = self._parse_identifier_or_keyword_as_name()
                elif self._current().type == TokenType.IDENTIFIER and not self._match_keywords(
                    "FROM",
                    "WHERE",
                    "GROUP",
                    "HAVING",
                    "ORDER",
                    "LIMIT",
                    "UNION",
                    "INTERSECT",
                    "EXCEPT",
                    "FOR",
                    "INTO",
                    "LATERAL",
                    "ON",
                    "INNER",
                    "LEFT",
                    "RIGHT",
                    "FULL",
                    "CROSS",
                    "JOIN",
                    "AND",
                    "OR",
                    "THEN",
                ):
                    alias = self._parse_identifier()

                columns.append(SelectColumn(expr=expr, alias=alias))

            if not self._match_punctuation(","):
                break
            self._advance()

        return columns

    # ─── FROM clause and JOINs ────────────────────────────────────────

    def _parse_from_clause(self) -> FromClause:
        """Parse a FROM clause with optional JOINs."""
        source = self._parse_table_ref()
        joins: list[JoinClause] = []

        while True:
            join = self._try_parse_join()
            if join is None:
                break
            joins.append(join)

        return FromClause(source=source, joins=joins)

    def _parse_table_ref(self) -> TableRef | SubqueryRef | FunctionRef:
        """Parse a table reference (name, subquery, or function)."""
        lateral = False
        if self._consume_keyword("LATERAL"):
            lateral = True

        # Subquery
        if self._match_punctuation("("):
            self._advance()
            subquery = self._parse_select()
            self._expect_punctuation(")")
            alias = self._try_parse_alias()
            ref = SubqueryRef(subquery=subquery, alias=alias)
            return ref

        # Table name or function
        name = self._parse_qualified_identifier()

        # Function call
        if self._match_punctuation("("):
            self._advance()
            args: list[Expression] = []
            if not self._match_punctuation(")"):
                args = self._parse_expression_list()
            self._expect_punctuation(")")

            alias = self._try_parse_alias()
            return FunctionRef(name=name, args=args, alias=alias, lateral=lateral)

        # Plain table reference
        schema = None
        table_name = name
        if "." in name:
            parts = name.split(".", 1)
            schema = parts[0]
            table_name = parts[1]

        alias = self._try_parse_alias()
        return TableRef(name=table_name, schema=schema, alias=alias)

    def _try_parse_join(self) -> JoinClause | None:
        """Try to parse a JOIN clause. Returns None if no JOIN found."""
        natural = False
        join_type = "INNER"

        if self._consume_keyword("NATURAL"):
            natural = True

        if self._match_keywords("INNER", "LEFT", "RIGHT", "FULL", "CROSS"):
            kw = self._advance().value
            if kw == "LEFT":
                join_type = "LEFT"
                self._consume_keyword("OUTER")
            elif kw == "RIGHT":
                join_type = "RIGHT"
                self._consume_keyword("OUTER")
            elif kw == "FULL":
                join_type = "FULL"
                self._consume_keyword("OUTER")
            elif kw == "CROSS":
                join_type = "CROSS"
            # INNER or default

        if self._consume_keyword("JOIN"):
            right = self._parse_table_ref()

            condition = None
            using_columns: list[str] = []

            if self._consume_keyword("ON"):
                condition = self._parse_expression()
            elif self._consume_keyword("USING"):
                self._expect_punctuation("(")
                using_columns = self._parse_identifier_list()
                self._expect_punctuation(")")

            return JoinClause(
                join_type=join_type,
                right=right,
                condition=condition,
                using_columns=using_columns,
                natural=natural,
            )

        # Also handle comma-join (implicit cross join)
        if self._match_punctuation(","):
            self._advance()
            right = self._parse_table_ref()
            return JoinClause(
                join_type="CROSS",
                right=right,
                condition=None,
            )

        return None

    # ─── INSERT ───────────────────────────────────────────────────────

    def _parse_insert(self) -> InsertStatement:
        """Parse an INSERT statement."""
        self._expect_keyword("INSERT")
        self._expect_keyword("INTO")

        table_name = self._parse_qualified_identifier()
        schema = None
        tname = table_name
        if "." in table_name:
            parts = table_name.split(".", 1)
            schema = parts[0]
            tname = parts[1]

        table = TableRef(name=tname, schema=schema)

        columns: list[str] = []
        if self._match_punctuation("("):
            self._advance()
            # Check if this is column list or VALUES
            if self._match_keywords("SELECT"):
                # INSERT INTO ... (SELECT ...)
                self._expect_punctuation(")")
                subquery = self._parse_select()
                stmt = InsertStatement(table=table, subquery=subquery)
                return self._parse_insert_conflict_returning(stmt)

            columns = self._parse_identifier_list()
            self._expect_punctuation(")")

        self._expect_keyword("VALUES")

        values: list[list[Expression]] = []
        while True:
            self._expect_punctuation("(")
            row = self._parse_expression_list()
            self._expect_punctuation(")")
            values.append(row)
            if not self._match_punctuation(","):
                break
            self._advance()

        stmt = InsertStatement(table=table, columns=columns, values=values)
        return self._parse_insert_conflict_returning(stmt)

    def _parse_insert_conflict_returning(self, stmt: InsertStatement) -> InsertStatement:
        """Parse ON CONFLICT and RETURNING clauses for INSERT."""
        # ON CONFLICT
        if self._match_keyword("ON"):
            self._advance()
            self._expect_keyword("CONFLICT")

            target = None
            if self._match_punctuation("("):
                self._advance()
                target_cols = self._parse_identifier_list()
                self._expect_punctuation(")")
                # Build a simple expression from the columns
                if len(target_cols) == 1:
                    target = ColumnRef(name=target_cols[0])
                else:
                    target = ColumnRef(name=", ".join(target_cols))
            elif self._consume_keyword("ON"):
                self._expect_keyword("CONSTRAINT")
                constraint_name = self._parse_identifier()
                target = ColumnRef(name=constraint_name)

            action = "NOTHING"
            update_assignments: list[Assignment] = []
            where_clause = None

            self._expect_keyword("DO")
            if self._consume_keyword("NOTHING"):
                action = "NOTHING"
            elif self._consume_keyword("UPDATE"):
                action = "UPDATE"
                self._expect_keyword("SET")
                update_assignments = self._parse_assignment_list()
                if self._consume_keyword("WHERE"):
                    where_clause = self._parse_expression()

            stmt.on_conflict = OnConflictClause(
                target=target,
                action=action,
                update_assignments=update_assignments,
                where_clause=where_clause,
            )

        # RETURNING
        if self._consume_keyword("RETURNING"):
            stmt.returning = self._parse_expression_list()

        return stmt

    # ─── UPDATE ───────────────────────────────────────────────────────

    def _parse_update(self) -> UpdateStatement:
        """Parse an UPDATE statement."""
        self._expect_keyword("UPDATE")

        table_name = self._parse_qualified_identifier()
        schema = None
        tname = table_name
        if "." in table_name:
            parts = table_name.split(".", 1)
            schema = parts[0]
            tname = parts[1]

        table = TableRef(name=tname, schema=schema)

        self._expect_keyword("SET")
        assignments = self._parse_assignment_list()

        from_clause = None
        where_clause = None

        # FROM clause (PostgreSQL extension)
        if self._consume_keyword("FROM"):
            from_clause = self._parse_from_clause()

        if self._consume_keyword("WHERE"):
            where_clause = self._parse_expression()

        stmt = UpdateStatement(
            table=table,
            assignments=assignments,
            from_clause=from_clause,
            where_clause=where_clause,
        )

        if self._consume_keyword("RETURNING"):
            stmt.returning = self._parse_expression_list()

        return stmt

    # ─── DELETE ───────────────────────────────────────────────────────

    def _parse_delete(self) -> DeleteStatement:
        """Parse a DELETE statement."""
        self._expect_keyword("DELETE")
        self._expect_keyword("FROM")

        table_name = self._parse_qualified_identifier()
        schema = None
        tname = table_name
        if "." in table_name:
            parts = table_name.split(".", 1)
            schema = parts[0]
            tname = parts[1]

        table = TableRef(name=tname, schema=schema)

        using_clause = None
        where_clause = None

        # USING clause (PostgreSQL extension)
        if self._consume_keyword("USING"):
            using_clause = self._parse_from_clause()

        if self._consume_keyword("WHERE"):
            where_clause = self._parse_expression()

        stmt = DeleteStatement(
            table=table,
            using_clause=using_clause,
            where_clause=where_clause,
        )

        if self._consume_keyword("RETURNING"):
            stmt.returning = self._parse_expression_list()

        return stmt

    # ─── DDL ──────────────────────────────────────────────────────────

    def _parse_create(self):
        """Parse a CREATE statement."""
        self._expect_keyword("CREATE")

        # CREATE OR REPLACE
        if self._consume_keyword("OR"):
            self._expect_keyword("REPLACE")

        # Temporary / Temp
        temporary = False
        if self._match_keywords("TEMPORARY", "TEMP"):
            self._advance()
            temporary = True

        if self._match_keyword("TABLE"):
            return self._parse_create_table(temporary=temporary)
        elif self._match_keyword("INDEX"):
            return self._parse_create_index()
        elif self._match_keyword("UNIQUE"):
            self._advance()
            if self._match_keyword("INDEX"):
                return self._parse_create_index(unique=True)
        elif self._match_keywords("MATERIALIZED"):
            # CREATE MATERIALIZED VIEW — treat as table for now
            self._advance()
            self._expect_keyword("VIEW")

        raise ParseError(
            f"Unexpected token after CREATE: {self._current().value!r}", self._current()
        )

    def _parse_create_table(self, temporary: bool = False) -> CreateTableStatement:
        """Parse a CREATE TABLE statement."""
        self._expect_keyword("TABLE")

        if_not_exists = False
        if self._consume_keyword("IF"):
            self._expect_keyword("NOT")
            self._expect_keyword("EXISTS")
            if_not_exists = True

        name = self._parse_qualified_identifier()
        schema = None
        table_name = name
        if "." in name:
            parts = name.split(".", 1)
            schema = parts[0]
            table_name = parts[1]

        self._expect_punctuation("(")

        columns: list[ColumnDefinition] = []
        constraints: list[TableConstraint] = []

        while not self._match_punctuation(")"):
            # Check if this is a table constraint
            if self._match_keywords(
                "PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "CONSTRAINT", "EXCLUDE"
            ):
                constraint = self._parse_table_constraint()
                constraints.append(constraint)
            else:
                col = self._parse_column_definition()
                columns.append(col)

            if not self._match_punctuation(","):
                break
            self._advance()

        self._expect_punctuation(")")

        # INHERITS
        inherits = None
        if self._consume_keyword("INHERITS"):
            self._expect_punctuation("(")
            inherits = self._parse_qualified_identifier()
            self._expect_punctuation(")")

        return CreateTableStatement(
            name=table_name,
            schema=schema,
            if_not_exists=if_not_exists,
            temporary=temporary,
            columns=columns,
            table_constraints=constraints,
            inherits=inherits,
        )

    def _parse_column_definition(self) -> ColumnDefinition:
        """Parse a column definition in CREATE TABLE."""
        name = self._parse_identifier()
        data_type, type_params = self._parse_data_type()

        not_null = False
        default = None
        primary_key = False
        unique = False
        references = None
        check = None
        auto_increment = False
        identity = None

        while True:
            if self._consume_keyword("NOT"):
                self._expect_keyword("NULL")
                not_null = True
            elif self._consume_keyword("NULL"):
                not_null = False
            elif self._consume_keyword("DEFAULT"):
                default = self._parse_expression()
            elif self._consume_keyword("PRIMARY"):
                self._expect_keyword("KEY")
                primary_key = True
            elif self._consume_keyword("UNIQUE"):
                unique = True
            elif self._consume_keyword("REFERENCES"):
                references = self._parse_qualified_identifier()
                if self._match_punctuation("("):
                    self._advance()
                    self._parse_identifier_list()
                    self._expect_punctuation(")")
                # ON DELETE / ON UPDATE
                if self._consume_keyword("ON"):
                    self._advance()  # DELETE or UPDATE
                    if self._match_keywords("CASCADE", "RESTRICT", "SET", "NO"):
                        self._advance()
            elif self._consume_keyword("CHECK"):
                self._expect_punctuation("(")
                check = self._parse_expression()
                self._expect_punctuation(")")
            elif self._consume_keyword("AUTO_INCREMENT"):
                auto_increment = True
            elif self._consume_keyword("GENERATED"):
                if self._consume_keyword("ALWAYS"):
                    identity = "ALWAYS"
                elif self._consume_keyword("BY"):
                    self._expect_keyword("DEFAULT")
                    identity = "BY DEFAULT"
                self._expect_keyword("AS")
                self._consume_keyword("IDENTITY")
            elif self._match_keyword("COLLATE"):
                self._advance()
                self._parse_identifier()  # Collation name
            else:
                break

        return ColumnDefinition(
            name=name,
            data_type=data_type,
            type_params=type_params,
            not_null=not_null,
            default=default,
            primary_key=primary_key,
            unique=unique,
            references=references,
            check=check,
            auto_increment=auto_increment,
            identity=identity,
        )

    def _parse_data_type(self) -> tuple[str, str | None]:
        """Parse a SQL data type, returning (type_name, type_params)."""
        token = self._current()

        if token.type != TokenType.KEYWORD and token.type != TokenType.IDENTIFIER:
            raise ParseError(f"Expected data type, got {token.value!r}", token)

        # Multi-word types
        type_parts = [self._advance().value]

        # CHARACTER VARYING, DOUBLE PRECISION, WITHOUT TIME ZONE, etc.
        while self._match_keywords("VARYING", "PRECISION", "TIME", "WITHOUT", "WITH", "ZONE"):
            type_parts.append(self._advance().value)

        data_type = " ".join(type_parts)
        type_params = None

        # Type parameters: (n), (n, m), (n, m, ...)
        if self._match_punctuation("("):
            self._advance()
            params: list[str] = []
            while not self._match_punctuation(")"):
                t = self._advance()
                params.append(t.value)
                if not self._match_punctuation(","):
                    break
                self._advance()
            self._expect_punctuation(")")
            type_params = ", ".join(params)

        # ARRAY suffix
        if self._match_punctuation("["):
            self._advance()
            if self._match_punctuation("]"):
                self._advance()
                data_type += "[]"

        return data_type, type_params

    def _parse_table_constraint(self) -> TableConstraint:
        """Parse a table-level constraint."""
        name = None

        if self._consume_keyword("CONSTRAINT"):
            name = self._parse_identifier()

        constraint_type = ""
        columns: list[str] = []
        reference_table = None
        reference_columns: list[str] = []
        on_delete = None
        on_update = None
        check_expression = None
        deferrable = False
        initially_deferred = False

        if self._consume_keyword("PRIMARY"):
            self._expect_keyword("KEY")
            constraint_type = "PRIMARY_KEY"
            self._expect_punctuation("(")
            columns = self._parse_identifier_list()
            self._expect_punctuation(")")

        elif self._consume_keyword("UNIQUE"):
            constraint_type = "UNIQUE"
            self._expect_punctuation("(")
            columns = self._parse_identifier_list()
            self._expect_punctuation(")")

        elif self._consume_keyword("FOREIGN"):
            self._expect_keyword("KEY")
            constraint_type = "FOREIGN_KEY"
            self._expect_punctuation("(")
            columns = self._parse_identifier_list()
            self._expect_punctuation(")")
            self._expect_keyword("REFERENCES")
            reference_table = self._parse_qualified_identifier()
            if self._match_punctuation("("):
                self._advance()
                reference_columns = self._parse_identifier_list()
                self._expect_punctuation(")")
            if self._match_keyword("ON"):
                self._advance()
                action = self._advance().value  # DELETE or UPDATE
                if self._match_keywords("CASCADE", "RESTRICT", "SET", "NO"):
                    ref_action = self._advance().value
                    if action == "DELETE":
                        on_delete = ref_action
                    else:
                        on_update = ref_action
            if self._consume_keyword("DEFERRABLE"):
                deferrable = True
                if self._consume_keyword("INITIALLY"):
                    if self._consume_keyword("DEFERRED"):
                        initially_deferred = True
                    else:
                        self._consume_keyword("IMMEDIATE")

        elif self._consume_keyword("CHECK"):
            constraint_type = "CHECK"
            self._expect_punctuation("(")
            check_expression = self._parse_expression()
            self._expect_punctuation(")")

        elif self._consume_keyword("EXCLUDE"):
            constraint_type = "EXCLUDE"
            self._expect_punctuation("(")
            # Skip the exclude constraint body for now
            depth = 1
            while depth > 0 and not self._match_type(TokenType.EOF):
                if self._match_punctuation("("):
                    depth += 1
                elif self._match_punctuation(")"):
                    depth -= 1
                if depth > 0:
                    self._advance()

        return TableConstraint(
            name=name,
            constraint_type=constraint_type,
            columns=columns,
            reference_table=reference_table,
            reference_columns=reference_columns,
            on_delete=on_delete,
            on_update=on_update,
            check_expression=check_expression,
            deferrable=deferrable,
            initially_deferred=initially_deferred,
        )

    def _parse_create_index(self, unique: bool = False) -> CreateIndexStatement:
        """Parse a CREATE INDEX statement."""
        self._expect_keyword("INDEX")

        if_not_exists = False
        if self._consume_keyword("IF"):
            self._expect_keyword("NOT")
            self._expect_keyword("EXISTS")
            if_not_exists = True

        name = self._parse_identifier()
        self._expect_keyword("ON")
        table = self._parse_qualified_identifier()

        method = None
        if self._consume_keyword("USING"):
            method = self._parse_identifier()

        self._expect_punctuation("(")
        index_exprs = self._parse_expression_list()
        self._expect_punctuation(")")

        where_clause = None
        if self._consume_keyword("WHERE"):
            where_clause = self._parse_expression()

        return CreateIndexStatement(
            name=name,
            table=table,
            columns=index_exprs,
            unique=unique,
            if_not_exists=if_not_exists,
            where_clause=where_clause,
            method=method,
        )

    def _parse_drop(self) -> DropTableStatement:
        """Parse a DROP statement."""
        self._expect_keyword("DROP")

        if self._consume_keyword("TABLE"):
            if_exists = False
            if self._consume_keyword("IF"):
                self._expect_keyword("EXISTS")
                if_exists = True

            name = self._parse_qualified_identifier()
            schema = None
            table_name = name
            if "." in name:
                parts = name.split(".", 1)
                schema = parts[0]
                table_name = parts[1]

            cascade = self._consume_keyword("CASCADE")
            self._consume_keyword("RESTRICT")

            return DropTableStatement(
                name=table_name,
                schema=schema,
                if_exists=if_exists,
                cascade=cascade,
            )

        raise ParseError(
            f"Expected TABLE after DROP, got {self._current().value!r}", self._current()
        )

    def _parse_alter(self) -> AlterTableStatement:
        """Parse an ALTER TABLE statement."""
        self._expect_keyword("ALTER")
        self._expect_keyword("TABLE")

        name = self._parse_qualified_identifier()
        actions: list[AlterAction] = []

        while True:
            if self._consume_keyword("ADD"):
                if self._consume_keyword("COLUMN"):
                    col = self._parse_column_definition()
                    actions.append(
                        AlterAction(
                            action_type="ADD_COLUMN",
                            column_name=col.name,
                            column_def=col,
                        )
                    )
                elif self._match_keywords(
                    "PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "CONSTRAINT", "EXCLUDE"
                ):
                    constraint = self._parse_table_constraint()
                    actions.append(
                        AlterAction(
                            action_type="ADD_CONSTRAINT",
                            constraint=constraint,
                        )
                    )
                else:
                    # ADD COLUMN (without COLUMN keyword)
                    col = self._parse_column_definition()
                    actions.append(
                        AlterAction(
                            action_type="ADD_COLUMN",
                            column_name=col.name,
                            column_def=col,
                        )
                    )

            elif self._consume_keyword("DROP"):
                self._consume_keyword("COLUMN")
                if_exists = self._consume_keyword("IF")
                if if_exists:
                    self._expect_keyword("EXISTS")
                col_name = self._parse_identifier()
                actions.append(
                    AlterAction(
                        action_type="DROP_COLUMN",
                        column_name=col_name,
                    )
                )

            elif self._consume_keyword("ALTER"):
                self._consume_keyword("COLUMN")
                col_name = self._parse_identifier()

                if self._consume_keyword("TYPE"):
                    data_type, type_params = self._parse_data_type()
                    actions.append(
                        AlterAction(
                            action_type="ALTER_COLUMN_TYPE",
                            column_name=col_name,
                            data_type=data_type,
                        )
                    )
                elif self._consume_keyword("SET"):
                    if self._consume_keyword("DEFAULT"):
                        default = self._parse_expression()
                        actions.append(
                            AlterAction(
                                action_type="SET_DEFAULT",
                                column_name=col_name,
                                default_value=default,
                            )
                        )
                    elif self._consume_keyword("NOT"):
                        self._expect_keyword("NULL")
                        actions.append(
                            AlterAction(
                                action_type="SET_NOT_NULL",
                                column_name=col_name,
                                nullable=False,
                            )
                        )
                elif self._consume_keyword("DROP"):
                    if self._consume_keyword("DEFAULT"):
                        actions.append(
                            AlterAction(
                                action_type="DROP_DEFAULT",
                                column_name=col_name,
                            )
                        )
                    elif self._consume_keyword("NOT"):
                        self._expect_keyword("NULL")
                        actions.append(
                            AlterAction(
                                action_type="DROP_NOT_NULL",
                                column_name=col_name,
                                nullable=True,
                            )
                        )

            elif self._consume_keyword("RENAME"):
                if self._consume_keyword("COLUMN"):
                    old_name = self._parse_identifier()
                    self._consume_keyword("TO")
                    new_name = self._parse_identifier()
                    actions.append(
                        AlterAction(
                            action_type="RENAME_COLUMN",
                            column_name=old_name,
                            new_name=new_name,
                        )
                    )
                elif self._consume_keyword("TO"):
                    new_name = self._parse_identifier()
                    actions.append(
                        AlterAction(
                            action_type="RENAME_TABLE",
                            new_name=new_name,
                        )
                    )

            else:
                break

            if not self._match_punctuation(","):
                break
            self._advance()

        return AlterTableStatement(name=name, actions=actions)

    def _parse_truncate(self):
        """Parse a TRUNCATE TABLE statement (simplified)."""
        self._expect_keyword("TRUNCATE")
        self._consume_keyword("TABLE")
        name = self._parse_qualified_identifier()
        self._consume_keyword("CASCADE")
        self._consume_keyword("RESTART")
        if self._consume_keyword("IDENTITY"):
            self._consume_keyword("CONTINUE")
        return DropTableStatement(name=name, if_exists=False)  # Simplified representation

    # ─── Expression parsing ───────────────────────────────────────────

    def _parse_expression(self) -> Expression:
        """Parse a full expression (entry point)."""
        return self._parse_or_expression()

    def _parse_or_expression(self) -> Expression:
        """Parse OR expressions (lowest precedence)."""
        left = self._parse_and_expression()

        while self._match_keyword("OR"):
            self._advance()
            right = self._parse_and_expression()
            left = BinaryOp(op="OR", left=left, right=right)

        return left

    def _parse_and_expression(self) -> Expression:
        """Parse AND expressions."""
        left = self._parse_not_expression()

        while self._match_keyword("AND"):
            self._advance()
            right = self._parse_not_expression()
            left = BinaryOp(op="AND", left=left, right=right)

        return left

    def _parse_not_expression(self) -> Expression:
        """Parse NOT expressions."""
        if self._match_keyword("NOT"):
            self._advance()
            operand = self._parse_not_expression()
            return UnaryOp(op="NOT", operand=operand)
        return self._parse_comparison()

    def _parse_comparison(self) -> Expression:
        """Parse comparison expressions."""
        left = self._parse_addition()

        while True:
            token = self._current()

            if token.type in (
                TokenType.EQ,
                TokenType.NEQ,
                TokenType.LT,
                TokenType.GT,
                TokenType.LTE,
                TokenType.GTE,
            ):
                op = self._advance().value
                right = self._parse_addition()
                left = BinaryOp(op=op, left=left, right=right)

            elif self._match_keyword("IS"):
                self._advance()
                negated = self._consume_keyword("NOT")
                self._expect_keyword("NULL")
                left = IsNullExpression(expr=left, negated=negated)

            elif self._match_keyword("IN"):
                self._advance()
                negated = False
                self._expect_punctuation("(")
                # Check if subquery or list
                if self._match_keyword("SELECT"):
                    subquery = self._parse_select()
                    self._expect_punctuation(")")
                    left = InExpression(expr=left, subquery=subquery, negated=negated)
                else:
                    values = self._parse_expression_list()
                    self._expect_punctuation(")")
                    left = InExpression(expr=left, values=values, negated=negated)

            elif self._match_keyword("NOT"):
                # NOT IN, NOT BETWEEN, NOT LIKE
                self._advance()
                if self._match_keyword("IN"):
                    self._advance()
                    self._expect_punctuation("(")
                    if self._match_keyword("SELECT"):
                        subquery = self._parse_select()
                        self._expect_punctuation(")")
                        left = InExpression(expr=left, subquery=subquery, negated=True)
                    else:
                        values = self._parse_expression_list()
                        self._expect_punctuation(")")
                        left = InExpression(expr=left, values=values, negated=True)
                elif self._match_keyword("BETWEEN"):
                    self._advance()
                    low = self._parse_addition()
                    self._expect_keyword("AND")
                    high = self._parse_addition()
                    left = BetweenExpression(expr=left, low=low, high=high, negated=True)
                elif self._match_keywords("LIKE", "ILIKE", "SIMILAR"):
                    op = self._advance().value
                    pattern = self._parse_addition()
                    escape = None
                    if self._consume_keyword("ESCAPE"):
                        esc_expr = self._parse_primary()
                        escape = (
                            esc_expr.value
                            if isinstance(esc_expr, Literal) and isinstance(esc_expr.value, str)
                            else None
                        )
                    left = LikeExpression(expr=left, pattern=pattern, escape=escape, negated=True)
                else:
                    # NOT without IN/BETWEEN/LIKE — treat as unary NOT
                    # Put NOT back conceptually by parsing as UnaryOp
                    right = self._parse_not_expression()
                    left = BinaryOp(op="AND", left=left, right=UnaryOp(op="NOT", operand=right))
                    break

            elif self._match_keyword("BETWEEN"):
                self._advance()
                low = self._parse_addition()
                self._expect_keyword("AND")
                high = self._parse_addition()
                left = BetweenExpression(expr=left, low=low, high=high)

            elif self._match_keywords("LIKE", "ILIKE", "SIMILAR"):
                op = self._advance().value
                pattern = self._parse_addition()
                escape = None
                if self._consume_keyword("ESCAPE"):
                    esc_token = self._advance()
                    escape = esc_token.value
                left = LikeExpression(expr=left, pattern=pattern, escape=escape)

            else:
                break

        return left

    def _parse_addition(self) -> Expression:
        """Parse addition/subtraction/concatenation."""
        left = self._parse_multiplication()

        while self._current().type in (TokenType.PLUS, TokenType.MINUS, TokenType.PIPE_PIPE):
            op = self._advance().value
            right = self._parse_multiplication()
            left = BinaryOp(op=op, left=left, right=right)

        return left

    def _parse_multiplication(self) -> Expression:
        """Parse multiplication/division/modulo."""
        left = self._parse_unary()

        while self._current().type in (TokenType.STAR, TokenType.SLASH, TokenType.PERCENT):
            op = self._advance().value
            right = self._parse_unary()
            left = BinaryOp(op=op, left=left, right=right)

        return left

    def _parse_unary(self) -> Expression:
        """Parse unary +/-."""
        if self._current().type == TokenType.MINUS:
            self._advance()
            operand = self._parse_unary()
            return UnaryOp(op="-", operand=operand)
        if self._current().type == TokenType.PLUS:
            self._advance()
            return self._parse_unary()
        return self._parse_type_cast()

    def _parse_type_cast(self) -> Expression:
        """Parse type cast expressions (::type)."""
        expr = self._parse_primary()

        while self._current().type == TokenType.PIPE_PIPE:
            # || is concatenation, not cast — handled in addition
            break

        if self._match_punctuation("::"):
            # PostgreSQL-style ::type cast
            self._advance()  # consume ::
            type_name = self._parse_data_type_name()
            expr = TypeCast(expr=expr, target_type=type_name)

        return expr

    def _parse_primary(self) -> Expression:
        """Parse a primary expression (literals, identifiers, parens, etc.)."""
        token = self._current()

        # NULL
        if token.keyword_is("NULL"):
            self._advance()
            return Literal(value=None, kind="null")

        # TRUE / FALSE
        if token.keyword_is("TRUE"):
            self._advance()
            return Literal(value=True, kind="boolean")
        if token.keyword_is("FALSE"):
            self._advance()
            return Literal(value=False, kind="boolean")

        # Numeric literals
        if token.type == TokenType.INTEGER:
            self._advance()
            return Literal(value=int(token.value), kind="integer")
        if token.type == TokenType.FLOAT:
            self._advance()
            return Literal(value=float(token.value), kind="float")
        if token.type == TokenType.HEX:
            self._advance()
            return Literal(value=token.value, kind="hex")

        # String literal
        if token.type == TokenType.STRING:
            self._advance()
            return Literal(value=token.value, kind="string")

        # Parameter
        if token.type == TokenType.PARAMETER:
            self._advance()
            index = None
            if token.value.startswith("$") and token.value[1:].isdigit():
                index = int(token.value[1:])
            return ParameterRef(name=token.value, index=index)

        # Parenthesized expression or subquery
        if token.type == TokenType.LPAREN:
            self._advance()

            # Check for subquery
            if self._match_keyword("SELECT"):
                subquery = self._parse_select()
                self._expect_punctuation(")")
                return SubqueryExpression(subquery=subquery)

            # Check for EXISTS (subquery)
            if self._match_keyword("EXISTS"):
                self._advance()
                self._expect_punctuation("(")
                subquery = self._parse_select()
                self._expect_punctuation(")")
                self._expect_punctuation(")")
                return ExistsExpression(subquery=subquery)

            expr = self._parse_expression()
            self._expect_punctuation(")")

            # Array access: expr[index]
            while self._match_punctuation("["):
                self._advance()
                index = self._parse_expression()
                if self._match_punctuation("]"):
                    self._advance()
                expr = ArrayAccess(array=expr, index=index)

            return expr

        # CASE expression
        if token.keyword_is("CASE"):
            return self._parse_case_expression()

        # CAST expression
        if token.keyword_is("CAST"):
            return self._parse_cast_expression()

        # EXISTS expression
        if token.keyword_is("EXISTS"):
            self._advance()
            self._expect_punctuation("(")
            subquery = self._parse_select()
            self._expect_punctuation(")")
            return ExistsExpression(subquery=subquery)

        # ARRAY constructor
        if token.keyword_is("ARRAY"):
            return self._parse_array_expression()

        # Identifier or keyword-as-identifier (column name, function name, etc.)
        if token.type in (TokenType.IDENTIFIER, TokenType.KEYWORD):
            name = self._advance().value

            # Qualified name: schema.table or table.column
            if self._match_punctuation("."):
                self._advance()

                # table.*
                if self._match_type(TokenType.STAR):
                    self._advance()
                    return Star(table=name)

                # table.column
                next_token = self._current()
                if next_token.type in (TokenType.IDENTIFIER, TokenType.KEYWORD):
                    col_name = self._advance().value
                    # Check for further qualification: schema.table.column
                    if self._match_punctuation("."):
                        self._advance()
                        third = self._advance().value
                        return ColumnRef(name=third, table=col_name, schema=name)
                    return ColumnRef(name=col_name, table=name)

            # table.function_call() — shouldn't normally happen but handle
            if self._match_punctuation("("):
                return self._parse_function_call(name)

            # PostgreSQL-style type cast: identifier::type
            if self._match_punctuation("::"):
                self._advance()  # consume ::
                type_name = self._parse_data_type_name()
                return TypeCast(expr=ColumnRef(name=name), target_type=type_name)

            # COLLATE
            if self._match_keyword("COLLATE"):
                self._advance()
                collation = self._parse_identifier()
                return CollateExpression(expr=ColumnRef(name=name), collation=collation)

            return ColumnRef(name=name)

        raise ParseError(
            f"Unexpected token in expression: {token.value!r} ({token.type.name})", token
        )

    def _parse_function_call(self, name: str) -> Expression:
        """Parse a function call after the name has been consumed."""
        self._expect_punctuation("(")

        # Check for DISTINCT
        distinct = self._consume_keyword("DISTINCT")

        args: list[Expression] = []

        # Check for empty args
        if self._match_punctuation(")"):
            self._advance()
        else:
            # * argument (e.g., COUNT(*))
            if self._match_type(TokenType.STAR):
                self._advance()
                self._expect_punctuation(")")
                args = [Star()]  # type: ignore[list-item]
                func = FunctionCall(name=name, args=args, distinct=distinct)
                return self._parse_post_function(func)

            args = self._parse_expression_list()
            self._expect_punctuation(")")

        func = FunctionCall(name=name, args=args, distinct=distinct)

        return self._parse_post_function(func)

    def _parse_post_function(self, func: FunctionCall) -> Expression:
        """Parse FILTER and OVER clauses after a function call."""
        # FILTER (WHERE ...)
        if self._consume_keyword("FILTER"):
            self._expect_punctuation("(")
            self._expect_keyword("WHERE")
            func.filter_clause = self._parse_expression()
            self._expect_punctuation(")")

        # OVER (...)
        if self._consume_keyword("OVER"):
            window = self._parse_window_spec()
            func.over_clause = window

        return func

    def _parse_window_spec(self) -> WindowSpec:
        """Parse a window specification."""
        # Named window or inline spec
        if self._current().type == TokenType.IDENTIFIER:
            # Named window reference
            _ = self._advance().value
            return WindowSpec()  # Reference by name — simplified

        self._expect_punctuation("(")

        partition_by: list[Expression] = []
        order_by: list[SortItem] = []
        frame_clause = None

        if self._consume_keyword("PARTITION"):
            self._expect_keyword("BY")
            partition_by = self._parse_expression_list()

        if self._match_keyword("ORDER"):
            self._advance()
            self._expect_keyword("BY")
            order_by = self._parse_order_by_list()

        # Frame clause
        if self._match_keywords("ROWS", "RANGE", "GROUPS"):
            frame_clause = self._parse_frame_clause()

        self._expect_punctuation(")")

        return WindowSpec(partition_by=partition_by, order_by=order_by, frame_clause=frame_clause)

    def _parse_frame_clause(self) -> FrameClause:
        """Parse a window frame clause."""
        mode = self._advance().value  # ROWS, RANGE, or GROUPS

        # BETWEEN start AND end
        self._expect_keyword("BETWEEN")
        start = self._parse_frame_bound()
        self._expect_keyword("AND")
        end = self._parse_frame_bound()

        return FrameClause(mode=mode, start=start, end=end)

    def _parse_frame_bound(self) -> FrameBound:
        """Parse a frame boundary."""
        if self._consume_keyword("UNBOUNDED"):
            if self._consume_keyword("PRECEDING"):
                return FrameBound(kind="UNBOUNDED_PRECEDING")
            elif self._consume_keyword("FOLLOWING"):
                return FrameBound(kind="UNBOUNDED_FOLLOWING")
        elif self._consume_keyword("CURRENT"):
            self._expect_keyword("ROW")
            return FrameBound(kind="CURRENT_ROW")
        elif self._consume_keyword("PRECEDING"):
            return FrameBound(kind="PRECEDING")
        elif self._consume_keyword("FOLLOWING"):
            return FrameBound(kind="FOLLOWING")
        else:
            # Numeric offset PRECEDING/FOLLOWING
            offset = self._parse_primary()
            if self._consume_keyword("PRECEDING"):
                return FrameBound(kind="PRECEDING", offset=offset)
            elif self._consume_keyword("FOLLOWING"):
                return FrameBound(kind="FOLLOWING", offset=offset)

        raise ParseError(f"Expected frame boundary, got {self._current().value!r}", self._current())

    def _parse_case_expression(self) -> CaseExpression:
        """Parse a CASE expression."""
        self._expect_keyword("CASE")

        operand = None
        when_clauses: list[WhenClause] = []
        else_clause = None

        # Simple CASE: CASE expr WHEN ...
        # Searched CASE: CASE WHEN ...
        if not self._match_keyword("WHEN"):
            operand = self._parse_expression()

        while self._consume_keyword("WHEN"):
            condition = self._parse_expression()
            self._expect_keyword("THEN")
            result = self._parse_expression()
            when_clauses.append(WhenClause(condition=condition, result=result))

        if self._consume_keyword("ELSE"):
            else_clause = self._parse_expression()

        self._expect_keyword("END")

        return CaseExpression(operand=operand, when_clauses=when_clauses, else_clause=else_clause)

    def _parse_cast_expression(self) -> CastExpression:
        """Parse a CAST(expr AS type) expression."""
        self._expect_keyword("CAST")
        self._expect_punctuation("(")
        expr = self._parse_expression()
        self._expect_keyword("AS")
        type_name, _ = self._parse_data_type()
        self._expect_punctuation(")")

        return CastExpression(expr=expr, target_type=type_name)

    def _parse_array_expression(self) -> ArrayExpression:
        """Parse an ARRAY[...] or ARRAY(SELECT ...) expression."""
        self._expect_keyword("ARRAY")

        if self._match_punctuation("("):
            # ARRAY(SELECT ...)
            self._advance()
            subquery = self._parse_select()
            self._expect_punctuation(")")
            return ArrayExpression(subquery=subquery)

        if self._match_punctuation("["):
            self._advance()
            elements = self._parse_expression_list()
            self._expect_punctuation("]")
            return ArrayExpression(elements=elements)

        return ArrayExpression()

    # ─── Helpers ───────────────────────────────────────────────────────

    def _parse_identifier(self) -> str:
        """Parse an identifier."""
        token = self._current()
        if token.type == TokenType.IDENTIFIER:
            return self._advance().value
        if token.type == TokenType.KEYWORD:
            # Some keywords can be used as identifiers in certain contexts
            return self._advance().value
        raise ParseError(f"Expected identifier, got {token.value!r} ({token.type.name})", token)

    def _parse_qualified_identifier(self) -> str:
        """Parse a potentially schema-qualified identifier (e.g., public.users)."""
        name = self._parse_identifier()
        while self._match_punctuation("."):
            self._advance()
            next_name = self._parse_identifier()
            name = f"{name}.{next_name}"
        return name

    def _parse_identifier_or_keyword_as_name(self) -> str:
        """Parse an identifier or keyword that can be used as a name/alias."""
        token = self._current()
        if token.type in (TokenType.IDENTIFIER, TokenType.KEYWORD):
            return self._advance().value
        raise ParseError(f"Expected name, got {token.value!r}", token)

    def _parse_identifier_list(self) -> list[str]:
        """Parse a comma-separated list of identifiers."""
        identifiers: list[str] = []
        while True:
            identifiers.append(self._parse_identifier())
            if not self._match_punctuation(","):
                break
            self._advance()
        return identifiers

    def _parse_expression_list(self) -> list[Expression]:
        """Parse a comma-separated list of expressions."""
        expressions: list[Expression] = []
        while True:
            expressions.append(self._parse_expression())
            if not self._match_punctuation(","):
                break
            self._advance()
        return expressions

    def _parse_assignment_list(self) -> list[Assignment]:
        """Parse a comma-separated list of assignments (col = expr)."""
        assignments: list[Assignment] = []
        while True:
            col_name = self._parse_identifier()
            self._expect(TokenType.EQ)
            value = self._parse_expression()
            assignments.append(Assignment(column=col_name, value=value))
            if not self._match_punctuation(","):
                break
            self._advance()
        return assignments

    def _parse_order_by_list(self) -> list[SortItem]:
        """Parse an ORDER BY list."""
        items: list[SortItem] = []
        while True:
            expr = self._parse_expression()
            ascending = True
            nulls_first = None

            if self._consume_keyword("ASC"):
                ascending = True
            elif self._consume_keyword("DESC"):
                ascending = False

            if self._consume_keyword("NULLS"):
                if self._consume_keyword("FIRST"):
                    nulls_first = True
                elif self._consume_keyword("LAST"):
                    nulls_first = False

            items.append(SortItem(expr=expr, ascending=ascending, nulls_first=nulls_first))

            if not self._match_punctuation(","):
                break
            self._advance()

        return items

    def _try_parse_alias(self) -> str | None:
        """Try to parse an optional alias (AS name or just name)."""
        if self._consume_keyword("AS"):
            return self._parse_identifier_or_keyword_as_name()

        # Implicit alias: next token is identifier or keyword-as-identifier
        # and not a keyword that starts a clause
        token = self._current()
        can_be_alias = token.type == TokenType.IDENTIFIER or (
            token.type == TokenType.KEYWORD
            and not self._match_keywords(
                "FROM",
                "WHERE",
                "GROUP",
                "HAVING",
                "ORDER",
                "LIMIT",
                "UNION",
                "INTERSECT",
                "EXCEPT",
                "FOR",
                "ON",
                "INNER",
                "LEFT",
                "RIGHT",
                "FULL",
                "CROSS",
                "JOIN",
                "NATURAL",
                "USING",
                "SET",
                "VALUES",
                "INTO",
                "AND",
                "OR",
                "WHEN",
                "THEN",
                "ELSE",
                "END",
                "BETWEEN",
                "IN",
                "LIKE",
                "RETURNING",
                "LATERAL",
                "SELECT",
                "INSERT",
                "UPDATE",
                "DELETE",
                "CREATE",
                "DROP",
                "ALTER",
                "WITH",
                "AS",
                "NOT",
                "NULL",
                "TRUE",
                "FALSE",
                "IS",
                "DISTINCT",
                "ALL",
                "ANY",
                "EXISTS",
                "CASE",
                "OVER",
                "PARTITION",
                "ROWS",
                "RANGE",
                "UNBOUNDED",
                "PRECEDING",
                "FOLLOWING",
                "CURRENT",
                "ROW",
                "GROUPS",
                "WINDOW",
            )
        )
        if can_be_alias:
            return self._advance().value

        return None

    def _expect_punctuation(self, value: str) -> Token:
        """Expect and consume a specific punctuation token."""
        if value == "(":
            return self._expect(TokenType.LPAREN)
        if value == ")":
            return self._expect(TokenType.RPAREN)
        if value == ",":
            return self._expect(TokenType.COMMA)
        if value == ";":
            return self._expect(TokenType.SEMICOLON)
        if value == ".":
            return self._expect(TokenType.DOT)
        if value == "::":
            t = self._current()
            if t.type == TokenType.COLON and t.value == "::":
                return self._advance()
            raise ParseError(f"Expected '::' but got {t.value!r}", t)
        if value == ":":
            t = self._current()
            if t.type == TokenType.COLON and t.value == ":":
                return self._advance()
            raise ParseError(f"Expected ':' but got {t.value!r}", t)
        raise ParseError(f"Unknown punctuation: {value!r}")

    def _parse_data_type_name(self) -> str:
        """Parse a data type name (for :: casts)."""
        parts = [self._parse_identifier()]
        while self._match_keywords("VARYING", "PRECISION", "WITHOUT", "WITH", "TIME", "ZONE"):
            parts.append(self._advance().value)
        # Type params
        if self._match_punctuation("("):
            self._advance()
            params: list[str] = []
            while not self._match_punctuation(")"):
                params.append(self._advance().value)
                if not self._match_punctuation(","):
                    break
                self._advance()
            self._expect_punctuation(")")
            parts.append(f"({', '.join(params)})")
        # Array suffix
        if self._match_punctuation("["):
            self._advance()
            if self._match_punctuation("]"):
                self._advance()
                parts.append("[]")
        return " ".join(parts)


def parse_sql(sql: str) -> SqlProgram:
    """Convenience function to parse a SQL string into an AST."""
    return Parser(sql).parse()
