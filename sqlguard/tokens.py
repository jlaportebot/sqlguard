"""SQL tokenizer for SQLGuard.

Breaks SQL text into a stream of typed tokens for use by the parser.
Handles keywords, identifiers, literals, operators, and punctuation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    """Token types produced by the SQL tokenizer."""

    # Literals
    INTEGER = auto()
    FLOAT = auto()
    STRING = auto()
    BINARY = auto()
    HEX = auto()
    BIT_STRING = auto()
    NATIONAL_STRING = auto()

    # Identifiers and keywords
    IDENTIFIER = auto()
    KEYWORD = auto()
    PARAMETER = auto()  # ? or $1 or :name

    # Operators
    PLUS = auto()  # +
    MINUS = auto()  # -
    STAR = auto()  # *
    SLASH = auto()  # /
    PERCENT = auto()  # %
    PIPE = auto()  # |
    PIPE_PIPE = auto()  # ||
    AMPERSAND = auto()  # &
    AMPERSAND_AMPERSAND = auto()  # &&
    CARET = auto()  # ^
    TILDE = auto()  # ~

    # Comparison
    EQ = auto()  # =
    NEQ = auto()  # != or <>
    LT = auto()  # <
    GT = auto()  # >
    LTE = auto()  # <=
    GTE = auto()  # >=

    # Assignment
    ASSIGN = auto()  # :=

    # Punctuation
    LPAREN = auto()  # (
    RPAREN = auto()  # )
    LBRACKET = auto()  # [
    RBRACKET = auto()  # ]
    LBRACE = auto()  # {
    RBRACE = auto()  # }
    COMMA = auto()  # ,
    SEMICOLON = auto()  # ;
    COLON = auto()  # :
    DOT = auto()  # .
    ARROW = auto()  # ->
    LONG_ARROW = auto()  # ->>
    FAT_ARROW = auto()  # =>

    # Special
    EOF = auto()


# SQL keywords recognized by the tokenizer
SQL_KEYWORDS: frozenset[str] = frozenset(
    {
        # DML
        "SELECT",
        "FROM",
        "WHERE",
        "INSERT",
        "INTO",
        "VALUES",
        "UPDATE",
        "SET",
        "DELETE",
        "MERGE",
        "USING",
        "RETURNING",
        # DDL
        "CREATE",
        "DROP",
        "ALTER",
        "TABLE",
        "INDEX",
        "VIEW",
        "SEQUENCE",
        "DATABASE",
        "SCHEMA",
        "TRIGGER",
        "FUNCTION",
        "PROCEDURE",
        "DOMAIN",
        "TYPE",
        "ENUM",
        "EXTENSION",
        "MATERIALIZED",
        "UNLOGGED",
        "TEMPORARY",
        "TEMP",
        "OR",
        "REPLACE",
        "IF",
        "EXISTS",
        "NOT",
        # Joins
        "JOIN",
        "INNER",
        "LEFT",
        "RIGHT",
        "FULL",
        "OUTER",
        "CROSS",
        "ON",
        "LATERAL",
        "NATURAL",
        # Clauses
        "AND",
        "IN",
        "IS",
        "NULL",
        "TRUE",
        "FALSE",
        "BETWEEN",
        "LIKE",
        "CASE",
        "WHEN",
        "THEN",
        "ELSE",
        "END",
        "AS",
        "DISTINCT",
        "ALL",
        "ANY",
        "SOME",
        "UNION",
        "INTERSECT",
        "EXCEPT",
        "GROUP",
        "BY",
        "HAVING",
        "ORDER",
        "ASC",
        "DESC",
        "LIMIT",
        "OFFSET",
        "FETCH",
        "NEXT",
        "ROWS",
        "ONLY",
        "FIRST",
        "TOP",
        # Modifiers
        "WITH",
        "RECURSIVE",
        "NO",
        "CYCLE",
        "SEARCH",
        "DEPTH",
        "FOR",
        "NOWAIT",
        "SKIP",
        "LOCKED",
        "SHARE",
        "KEY",
        # Constraints
        "PRIMARY",
        "FOREIGN",
        "REFERENCES",
        "UNIQUE",
        "CHECK",
        "DEFAULT",
        "CONSTRAINT",
        "DEFERRABLE",
        "DEFERRED",
        "INITIALLY",
        "IMMEDIATE",
        "CASCADE",
        "RESTRICT",
        "ACTION",
        # Data types
        "SMALLINT",
        "INTEGER",
        "INT",
        "BIGINT",
        "SERIAL",
        "BIGSERIAL",
        "DECIMAL",
        "NUMERIC",
        "REAL",
        "DOUBLE",
        "PRECISION",
        "FLOAT",
        "CHAR",
        "CHARACTER",
        "VARYING",
        "VARCHAR",
        "TEXT",
        "STRING",
        "BOOLEAN",
        "BOOL",
        "DATE",
        "TIME",
        "TIMESTAMP",
        "INTERVAL",
        "ZONE",
        "WITHOUT",
        "BYTEA",
        "BLOB",
        "JSON",
        "JSONB",
        "UUID",
        "INET",
        "CIDR",
        "MACADDR",
        "ARRAY",
        "RECORD",
        # Aggregates and functions
        "COUNT",
        "SUM",
        "AVG",
        "MIN",
        "MAX",
        "COALESCE",
        "NULLIF",
        "CAST",
        "EXTRACT",
        "EPOCH",
        "YEAR",
        "MONTH",
        "DAY",
        "HOUR",
        "MINUTE",
        "SECOND",
        "OVER",
        "PARTITION",
        "WINDOW",
        "ROW",
        "RANGE",
        "UNBOUNDED",
        "PRECEDING",
        "FOLLOWING",
        "CURRENT",
        "ROW_NUMBER",
        "RANK",
        "DENSE_RANK",
        "PERCENT_RANK",
        "CUME_DIST",
        "NTILE",
        "LAG",
        "LEAD",
        "FIRST_VALUE",
        "LAST_VALUE",
        "NTH_VALUE",
        # Other
        "GRANT",
        "REVOKE",
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "SAVEPOINT",
        "RELEASE",
        "TRANSACTION",
        "ISOLATION",
        "LEVEL",
        "SERIALIZABLE",
        "REPEATABLE",
        "READ",
        "COMMITTED",
        "UNCOMMITTED",
        "WRITE",
        "ANALYZE",
        "EXPLAIN",
        "VACUUM",
        "REINDEX",
        "TRUNCATE",
        "CLUSTER",
        "COMMENT",
        "SECURITY",
        "POLICY",
        "FORCE",
        "OWNER",
        "TABLESPACE",
        "STORAGE",
        "TABLESAMPLE",
        "BERNOULLI",
        "SYSTEM",
        "RESTART",
        "CONTINUE",
        "IDENTITY",
        "GENERATED",
        "ALWAYS",
        "ENABLE",
        "DISABLE",
        "VALIDATE",
        "INVALIDATE",
        "ADD",
        "COLUMN",
        "RENAME",
        "TO",
        "AFTER",
        "BEFORE",
        "INHERIT",
        "INHERITS",
        "OF",
        "NONE",
        "OVERLAY",
        "PLACING",
        "SIMILAR",
        "ESCAPE",
        "COLLATE",
        "COLLATION",
        "CONcurrently",
        "EXTENDED",
        "MAIN",
        "SLICE",
        "STRICT",
        "VOLATILE",
        "STABLE",
        "IMMUTABLE",
        "LEAKPROOF",
        "RETURNS",
        "LANGUAGE",
        "PLPGSQL",
        "SQL",
        "C",
        "INTERNAL",
        "HANDLER",
        "EXECUTE",
        "PERFORM",
        "RAISE",
        "NOTICE",
        "EXCEPTION",
        "DEBUG",
        "LOG",
        "INFO",
        "WARNING",
        "ASSERT",
        "RETURN",
        "QUERY",
        "FOUND",
        "LOOP",
        "WHILE",
        "EXIT",
        "FOREACH",
        "REVERSE",
        "DECLARE",
        "ELSIF",
        "CONFLICT",
        "NOTHING",
        "DO",
        "OVERRIDING",
        "USER",
        "VALUE",
        "CONVERT",
        "NULLS",
        "LAST",
        "ENCRYPTED",
        "PASSWORD",
        "ENCRYPTION",
        "SUPERUSER",
        "NOSUPERUSER",
        "CREATEDB",
        "NOCREATEDB",
        "CREATEROLE",
        "NOCREATEROLE",
        "NOINHERIT",
        "LOGIN",
        "NOLOGIN",
        "CONNECTION",
        "REPLICATION",
        "NOREPLICATION",
        "BYPASSRLS",
        "NOBYPASSRLS",
        "ALLOW_CONNECTIONS",
        "LC_COLLATE",
        "LC_CTYPE",
        "TEMPLATE",
        "ENCODING",
        "LOCATION",
    }
)


@dataclass
class Token:
    """A single SQL token."""

    type: TokenType
    value: str
    line: int = 1
    column: int = 1

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, line={self.line}, col={self.column})"

    @property
    def is_keyword(self) -> bool:
        return self.type == TokenType.KEYWORD

    @property
    def is_identifier(self) -> bool:
        return self.type == TokenType.IDENTIFIER

    @property
    def is_literal(self) -> bool:
        return self.type in (
            TokenType.INTEGER,
            TokenType.FLOAT,
            TokenType.STRING,
            TokenType.BINARY,
            TokenType.HEX,
            TokenType.BIT_STRING,
        )

    def keyword_is(self, kw: str) -> bool:
        """Check if this is a keyword token matching the given keyword (case-insensitive)."""
        return self.type == TokenType.KEYWORD and self.value.upper() == kw.upper()


class TokenizerError(Exception):
    """Error raised when the tokenizer encounters invalid input."""

    def __init__(self, message: str, line: int = 0, column: int = 0) -> None:
        self.line = line
        self.column = column
        super().__init__(f"Tokenizer error at line {line}, column {column}: {message}")


class Tokenizer:
    """SQL tokenizer that breaks a SQL string into a stream of Token objects.

    Handles:
    - SQL keywords (case-insensitive)
    - Quoted identifiers ("name" or `name` or [name])
    - String literals ('text' and E'text')
    - Numeric literals (integer, float, hex)
    - Bit strings (B'1010' and X'FF')
    - Parameters (?, $1, :name)
    - Operators and punctuation
    - Comments (-- and /* */)
    """

    def __init__(self, sql: str) -> None:
        self.sql = sql
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens: list[Token] = []

    def tokenize(self) -> list[Token]:
        """Tokenize the SQL string and return a list of tokens."""
        while self.pos < len(self.sql):
            self._skip_whitespace_and_comments()
            if self.pos >= len(self.sql):
                break

            ch = self.sql[self.pos]

            # String literal
            if ch == "'" or (ch in "Ee" and self._peek_string_prefix()):
                self._read_string()
            # Numeric literal
            elif ch.isdigit():
                self._read_number()
            # Hex literal (0x prefix)
            elif ch == "0" and self.pos + 1 < len(self.sql) and self.sql[self.pos + 1] in "xX":
                self._read_hex()
            # Identifier or keyword
            elif ch.isalpha() or ch == "_":
                self._read_identifier_or_keyword()
            # Quoted identifier
            elif ch == '"':
                self._read_quoted_identifier('"')
            elif ch == "`":
                self._read_quoted_identifier("`")
            elif ch == "[":
                self._read_bracketed_identifier()
            # Parameters
            elif ch == "?":
                self._add_token(TokenType.PARAMETER, "?")
                self._advance()
            elif ch == "$":
                self._read_dollar_parameter()
            elif ch == ":":
                if self._peek(1) == ":":
                    self._add_token(TokenType.COLON, "::")
                    self._advance(2)
                elif self.pos + 1 < len(self.sql) and (
                    self.sql[self.pos + 1].isalpha() or self.sql[self.pos + 1] == "_"
                ):
                    self._read_named_parameter()
                else:
                    self._add_token(TokenType.COLON, ":")
                    self._advance()
            # Operators and punctuation
            elif ch == "(":
                self._add_token(TokenType.LPAREN, "(")
                self._advance()
            elif ch == ")":
                self._add_token(TokenType.RPAREN, ")")
                self._advance()
            elif ch == "[":
                self._add_token(TokenType.LBRACKET, "[")
                self._advance()
            elif ch == "]":
                self._add_token(TokenType.RBRACKET, "]")
                self._advance()
            elif ch == "{":
                self._add_token(TokenType.LBRACE, "{")
                self._advance()
            elif ch == "}":
                self._add_token(TokenType.RBRACE, "}")
                self._advance()
            elif ch == ",":
                self._add_token(TokenType.COMMA, ",")
                self._advance()
            elif ch == ";":
                self._add_token(TokenType.SEMICOLON, ";")
                self._advance()
            elif ch == ".":
                self._add_token(TokenType.DOT, ".")
                self._advance()
            elif ch == "+":
                self._add_token(TokenType.PLUS, "+")
                self._advance()
            elif ch == "-":
                if self._peek(1) == ">":
                    if self._peek(2) == ">":
                        self._add_token(TokenType.LONG_ARROW, "->>")
                        self._advance(3)
                    else:
                        self._add_token(TokenType.ARROW, "->")
                        self._advance(2)
                else:
                    self._add_token(TokenType.MINUS, "-")
                    self._advance()
            elif ch == "*":
                self._add_token(TokenType.STAR, "*")
                self._advance()
            elif ch == "/":
                self._add_token(TokenType.SLASH, "/")
                self._advance()
            elif ch == "%":
                self._add_token(TokenType.PERCENT, "%")
                self._advance()
            elif ch == "|":
                if self._peek(1) == "|":
                    self._add_token(TokenType.PIPE_PIPE, "||")
                    self._advance(2)
                else:
                    self._add_token(TokenType.PIPE, "|")
                    self._advance()
            elif ch == "&":
                if self._peek(1) == "&":
                    self._add_token(TokenType.AMPERSAND_AMPERSAND, "&&")
                    self._advance(2)
                else:
                    self._add_token(TokenType.AMPERSAND, "&")
                    self._advance()
            elif ch == "^":
                self._add_token(TokenType.CARET, "^")
                self._advance()
            elif ch == "~":
                self._add_token(TokenType.TILDE, "~")
                self._advance()
            elif ch == "=":
                if self._peek(1) == ">":
                    self._add_token(TokenType.FAT_ARROW, "=>")
                    self._advance(2)
                else:
                    self._add_token(TokenType.EQ, "=")
                    self._advance()
            elif ch == "<":
                if self._peek(1) == "=":
                    self._add_token(TokenType.LTE, "<=")
                    self._advance(2)
                elif self._peek(1) == ">":
                    self._add_token(TokenType.NEQ, "<>")
                    self._advance(2)
                else:
                    self._add_token(TokenType.LT, "<")
                    self._advance()
            elif ch == ">":
                if self._peek(1) == "=":
                    self._add_token(TokenType.GTE, ">=")
                    self._advance(2)
                else:
                    self._add_token(TokenType.GT, ">")
                    self._advance()
            elif ch == "!":
                if self._peek(1) == "=":
                    self._add_token(TokenType.NEQ, "!=")
                    self._advance(2)
                else:
                    raise TokenizerError(f"Unexpected character: '{ch}'", self.line, self.column)
            elif ch == ":":
                self._add_token(TokenType.COLON, ":")
                self._advance()
            else:
                raise TokenizerError(f"Unexpected character: '{ch}'", self.line, self.column)

        self._add_token(TokenType.EOF, "", self.line, self.column)
        return self.tokens

    def _advance(self, n: int = 1) -> None:
        """Advance the position by n characters, tracking line/column."""
        for _ in range(n):
            if self.pos < len(self.sql):
                if self.sql[self.pos] == "\n":
                    self.line += 1
                    self.column = 1
                else:
                    self.column += 1
                self.pos += 1

    def _peek(self, offset: int = 0) -> str:
        """Look ahead at a character without advancing."""
        idx = self.pos + offset
        if idx < len(self.sql):
            return self.sql[idx]
        return ""

    def _peek_string_prefix(self) -> bool:
        """Check if current position is an E' or e' string prefix."""
        return self.pos + 1 < len(self.sql) and self.sql[self.pos + 1] == "'"

    def _skip_whitespace_and_comments(self) -> None:
        """Skip whitespace and SQL comments."""
        while self.pos < len(self.sql):
            ch = self.sql[self.pos]

            # Whitespace
            if ch in " \t\r\n":
                self._advance()
                continue

            # Line comment: --
            if ch == "-" and self._peek(1) == "-":
                self._skip_line_comment()
                continue

            # Block comment: /* ... */
            if ch == "/" and self._peek(1) == "*":
                self._skip_block_comment()
                continue

            break

    def _skip_line_comment(self) -> None:
        """Skip a -- line comment."""
        while self.pos < len(self.sql) and self.sql[self.pos] != "\n":
            self._advance()
        # Don't skip the newline — let _advance handle it in the main loop

    def _skip_block_comment(self) -> None:
        """Skip a /* ... */ block comment."""
        self._advance(2)  # Skip /*
        depth = 1
        while self.pos < len(self.sql) and depth > 0:
            if self.sql[self.pos] == "/" and self._peek(1) == "*":
                depth += 1
                self._advance(2)
            elif self.sql[self.pos] == "*" and self._peek(1) == "/":
                depth -= 1
                self._advance(2)
            else:
                self._advance()
        if depth > 0:
            raise TokenizerError("Unterminated block comment", self.line, self.column)

    def _add_token(
        self, type_: TokenType, value: str, line: int | None = None, column: int | None = None
    ) -> None:
        """Add a token to the list."""
        self.tokens.append(
            Token(
                type=type_,
                value=value,
                line=line or self.line,
                column=column or self.column,
            )
        )

    def _read_string(self) -> None:
        """Read a string literal (single-quoted)."""
        start_line = self.line
        start_col = self.column
        is_escaped = False

        # Check for E' prefix (escaped string)
        if self.sql[self.pos] in "Ee":
            is_escaped = True
            self._advance()

        self._advance()  # Skip opening quote
        value_parts: list[str] = []

        while self.pos < len(self.sql):
            ch = self.sql[self.pos]

            if ch == "'":
                # Check for escaped single quote ''
                if self._peek(1) == "'":
                    value_parts.append("'")
                    self._advance(2)
                else:
                    self._advance()  # Skip closing quote
                    break
            elif ch == "\\" and is_escaped:
                # Handle escape sequences in E-strings
                next_ch = self._peek(1)
                escape_map = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'"}
                if next_ch in escape_map:
                    value_parts.append(escape_map[next_ch])
                    self._advance(2)
                else:
                    value_parts.append(ch)
                    self._advance()
            else:
                value_parts.append(ch)
                self._advance()

        self._add_token(TokenType.STRING, "".join(value_parts), start_line, start_col)

    def _read_number(self) -> None:
        """Read a numeric literal (integer or float)."""
        start_line = self.line
        start_col = self.column
        start_pos = self.pos

        # Check for hex: 0x prefix
        if (
            self.sql[self.pos] == "0"
            and self.pos + 1 < len(self.sql)
            and self.sql[self.pos + 1] in "xX"
        ):
            self._read_hex()
            return

        is_float = False

        # Read digits
        while self.pos < len(self.sql) and self.sql[self.pos].isdigit():
            self._advance()

        # Decimal point
        if (
            self.pos < len(self.sql)
            and self.sql[self.pos] == "."
            and self.pos + 1 < len(self.sql)
            and self.sql[self.pos + 1].isdigit()
        ):
            # Make sure it's not a dot-separated identifier (e.g., table.column)
            is_float = True
            self._advance()  # Skip dot
            while self.pos < len(self.sql) and self.sql[self.pos].isdigit():
                self._advance()

        # Scientific notation
        if self.pos < len(self.sql) and self.sql[self.pos] in "eE":
            is_float = True
            self._advance()
            if self.pos < len(self.sql) and self.sql[self.pos] in "+-":
                self._advance()
            while self.pos < len(self.sql) and self.sql[self.pos].isdigit():
                self._advance()

        value = self.sql[start_pos : self.pos]
        token_type = TokenType.FLOAT if is_float else TokenType.INTEGER
        self._add_token(token_type, value, start_line, start_col)

    def _read_hex(self) -> None:
        """Read a hex literal (0x...)."""
        start_line = self.line
        start_col = self.column
        start_pos = self.pos

        self._advance(2)  # Skip 0x
        while self.pos < len(self.sql) and (
            self.sql[self.pos].isdigit() or self.sql[self.pos].lower() in "abcdef"
        ):
            self._advance()

        value = self.sql[start_pos : self.pos]
        self._add_token(TokenType.HEX, value, start_line, start_col)

    def _read_identifier_or_keyword(self) -> None:
        """Read an identifier or keyword."""
        start_line = self.line
        start_col = self.column
        start_pos = self.pos

        while self.pos < len(self.sql) and (
            self.sql[self.pos].isalnum() or self.sql[self.pos] == "_"
        ):
            self._advance()

        value = self.sql[start_pos : self.pos]

        # Check if it's a keyword
        if value.upper() in SQL_KEYWORDS:
            self._add_token(TokenType.KEYWORD, value.upper(), start_line, start_col)
        else:
            self._add_token(TokenType.IDENTIFIER, value, start_line, start_col)

    def _read_quoted_identifier(self, quote_char: str) -> None:
        """Read a quoted identifier ("name" or `name`)."""
        start_line = self.line
        start_col = self.column
        self._advance()  # Skip opening quote
        value_parts: list[str] = []

        while self.pos < len(self.sql):
            ch = self.sql[self.pos]
            if ch == quote_char:
                # Check for escaped quote
                if self._peek(1) == quote_char:
                    value_parts.append(quote_char)
                    self._advance(2)
                else:
                    self._advance()  # Skip closing quote
                    break
            else:
                value_parts.append(ch)
                self._advance()

        self._add_token(TokenType.IDENTIFIER, "".join(value_parts), start_line, start_col)

    def _read_bracketed_identifier(self) -> None:
        """Read a bracketed identifier ([name] — SQL Server style)."""
        start_line = self.line
        start_col = self.column
        self._advance()  # Skip [
        value_parts: list[str] = []

        while self.pos < len(self.sql):
            ch = self.sql[self.pos]
            if ch == "]":
                self._advance()
                break
            else:
                value_parts.append(ch)
                self._advance()

        self._add_token(TokenType.IDENTIFIER, "".join(value_parts), start_line, start_col)

    def _read_dollar_parameter(self) -> None:
        """Read a dollar-sign parameter ($1, $2, etc.)."""
        start_line = self.line
        start_col = self.column
        start_pos = self.pos

        self._advance()  # Skip $
        while self.pos < len(self.sql) and self.sql[self.pos].isdigit():
            self._advance()

        value = self.sql[start_pos : self.pos]
        self._add_token(TokenType.PARAMETER, value, start_line, start_col)

    def _read_named_parameter(self) -> None:
        """Read a named parameter (:name)."""
        start_line = self.line
        start_col = self.column
        start_pos = self.pos

        self._advance()  # Skip :
        while self.pos < len(self.sql) and (
            self.sql[self.pos].isalnum() or self.sql[self.pos] == "_"
        ):
            self._advance()

        value = self.sql[start_pos : self.pos]
        self._add_token(TokenType.PARAMETER, value, start_line, start_col)

    def _read_bit_string(self) -> None:
        """Read a bit string literal (B'1010' or X'FF')."""
        start_line = self.line
        start_col = self.column
        prefix = self.sql[self.pos].upper()
        self._advance()  # Skip B or X
        self._advance()  # Skip opening quote
        value_parts: list[str] = []

        while self.pos < len(self.sql) and self.sql[self.pos] != "'":
            value_parts.append(self.sql[self.pos])
            self._advance()

        if self.pos < len(self.sql):
            self._advance()  # Skip closing quote

        token_type = TokenType.BIT_STRING if prefix == "B" else TokenType.HEX
        self._add_token(token_type, "".join(value_parts), start_line, start_col)


def tokenize(sql: str) -> list[Token]:
    """Convenience function to tokenize a SQL string."""
    return Tokenizer(sql).tokenize()
