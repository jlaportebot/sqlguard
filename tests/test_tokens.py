"""Tests for sqlguard.tokens module."""

import pytest

from sqlguard.tokens import Token, TokenizerError, TokenType, tokenize


class TestTokenizerBasic:
    """Test basic tokenization."""

    def test_empty_string(self):
        tokens = tokenize("")
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.EOF

    def test_whitespace_only(self):
        tokens = tokenize("   \n\t  ")
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.EOF

    def test_simple_keyword(self):
        tokens = tokenize("SELECT")
        assert tokens[0].type == TokenType.KEYWORD
        assert tokens[0].value == "SELECT"

    def test_keyword_case_insensitive(self):
        tokens = tokenize("select")
        assert tokens[0].type == TokenType.KEYWORD
        assert tokens[0].value == "SELECT"

    def test_mixed_case_keyword(self):
        tokens = tokenize("SeLeCt")
        assert tokens[0].type == TokenType.KEYWORD
        assert tokens[0].value == "SELECT"

    def test_identifier(self):
        tokens = tokenize("users")
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == "users"

    def test_underscore_identifier(self):
        tokens = tokenize("user_id")
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == "user_id"

    def test_quoted_identifier_double(self):
        tokens = tokenize('"my table"')
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == "my table"

    def test_quoted_identifier_backtick(self):
        tokens = tokenize("`my column`")
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == "my column"


class TestTokenizerLiterals:
    """Test literal tokenization."""

    def test_integer(self):
        tokens = tokenize("42")
        assert tokens[0].type == TokenType.INTEGER
        assert tokens[0].value == "42"

    def test_negative_integer(self):
        tokens = tokenize("-5")
        assert tokens[0].type == TokenType.MINUS
        assert tokens[1].type == TokenType.INTEGER

    def test_float(self):
        tokens = tokenize("3.14")
        assert tokens[0].type == TokenType.FLOAT
        assert tokens[0].value == "3.14"

    def test_scientific_notation(self):
        tokens = tokenize("1e10")
        assert tokens[0].type == TokenType.FLOAT

    def test_string_literal(self):
        tokens = tokenize("'hello world'")
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "hello world"

    def test_escaped_string(self):
        tokens = tokenize("E'line1\\nline2'")
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "line1\nline2"

    def test_string_with_escaped_quote(self):
        tokens = tokenize("'it''s fine'")
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "it's fine"

    def test_boolean_keywords(self):
        tokens = tokenize("TRUE FALSE")
        assert tokens[0].type == TokenType.KEYWORD
        assert tokens[0].value == "TRUE"
        assert tokens[1].type == TokenType.KEYWORD
        assert tokens[1].value == "FALSE"

    def test_null_keyword(self):
        tokens = tokenize("NULL")
        assert tokens[0].type == TokenType.KEYWORD
        assert tokens[0].value == "NULL"

    def test_hex_literal(self):
        tokens = tokenize("0xFF")
        assert tokens[0].type == TokenType.HEX
        assert tokens[0].value == "0xFF"


class TestTokenizerOperators:
    """Test operator tokenization."""

    def test_comparison_operators(self):
        tokens = tokenize("= <> < > <= >=")
        types = [t.type for t in tokens if t.type != TokenType.EOF]
        assert types == [
            TokenType.EQ,
            TokenType.NEQ,
            TokenType.LT,
            TokenType.GT,
            TokenType.LTE,
            TokenType.GTE,
        ]

    def test_not_equal(self):
        tokens = tokenize("!=")
        assert tokens[0].type == TokenType.NEQ

    def test_arithmetic_operators(self):
        tokens = tokenize("+ - * / %")
        types = [t.type for t in tokens if t.type != TokenType.EOF]
        assert types == [
            TokenType.PLUS,
            TokenType.MINUS,
            TokenType.STAR,
            TokenType.SLASH,
            TokenType.PERCENT,
        ]

    def test_concatenation(self):
        tokens = tokenize("||")
        assert tokens[0].type == TokenType.PIPE_PIPE

    def test_arrow_operators(self):
        tokens = tokenize("-> ->>")
        assert tokens[0].type == TokenType.ARROW
        assert tokens[1].type == TokenType.LONG_ARROW

    def test_fat_arrow(self):
        tokens = tokenize("=>")
        assert tokens[0].type == TokenType.FAT_ARROW


class TestTokenizerPunctuation:
    """Test punctuation tokenization."""

    def test_parentheses(self):
        tokens = tokenize("()")
        assert tokens[0].type == TokenType.LPAREN
        assert tokens[1].type == TokenType.RPAREN

    def test_comma(self):
        tokens = tokenize(",")
        assert tokens[0].type == TokenType.COMMA

    def test_semicolon(self):
        tokens = tokenize(";")
        assert tokens[0].type == TokenType.SEMICOLON

    def test_dot(self):
        tokens = tokenize(".")
        assert tokens[0].type == TokenType.DOT


class TestTokenizerParameters:
    """Test parameter tokenization."""

    def test_question_mark(self):
        tokens = tokenize("?")
        assert tokens[0].type == TokenType.PARAMETER
        assert tokens[0].value == "?"

    def test_dollar_parameter(self):
        tokens = tokenize("$1")
        assert tokens[0].type == TokenType.PARAMETER
        assert tokens[0].value == "$1"

    def test_named_parameter(self):
        tokens = tokenize(":name")
        assert tokens[0].type == TokenType.PARAMETER
        assert tokens[0].value == ":name"


class TestTokenizerComments:
    """Test comment handling."""

    def test_line_comment(self):
        tokens = tokenize("SELECT -- this is a comment\nFROM users")
        keywords = [t.value for t in tokens if t.type == TokenType.KEYWORD]
        assert keywords == ["SELECT", "FROM"]

    def test_block_comment(self):
        tokens = tokenize("SELECT /* comment */ FROM users")
        keywords = [t.value for t in tokens if t.type == TokenType.KEYWORD]
        assert keywords == ["SELECT", "FROM"]

    def test_multiline_block_comment(self):
        tokens = tokenize("/* line1\nline2\nline3 */ SELECT")
        assert tokens[0].type == TokenType.KEYWORD
        assert tokens[0].value == "SELECT"


class TestTokenizerComplex:
    """Test complex SQL tokenization."""

    def test_simple_select(self):
        tokens = tokenize("SELECT id, name FROM users WHERE id = 1")
        values = [t.value for t in tokens if t.type != TokenType.EOF]
        assert "SELECT" in values
        assert "FROM" in values
        assert "WHERE" in values
        assert "users" in values

    def test_qualified_name(self):
        tokens = tokenize("public.users")
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == "public"
        assert tokens[1].type == TokenType.DOT
        assert tokens[2].type == TokenType.IDENTIFIER
        assert tokens[2].value == "users"

    def test_function_call(self):
        tokens = tokenize("COUNT(*)")
        assert tokens[0].type == TokenType.KEYWORD
        assert tokens[0].value == "COUNT"
        assert tokens[1].type == TokenType.LPAREN
        assert tokens[2].type == TokenType.STAR
        assert tokens[3].type == TokenType.RPAREN

    def test_multiple_statements(self):
        tokens = tokenize("SELECT 1; SELECT 2;")
        semicolons = [t for t in tokens if t.type == TokenType.SEMICOLON]
        assert len(semicolons) == 2

    def test_line_tracking(self):
        tokens = tokenize("SELECT\nFROM\nusers")
        select_token = tokens[0]
        assert select_token.line == 1
        from_token = [t for t in tokens if t.value == "FROM"][0]
        assert from_token.line == 2
        users_token = [t for t in tokens if t.value == "users"][0]
        assert users_token.line == 3

    def test_unterminated_block_comment(self):
        with pytest.raises(TokenizerError, match="Unterminated"):
            tokenize("/* this never ends")

    def test_unexpected_character(self):
        with pytest.raises(TokenizerError, match="Unexpected"):
            tokenize("@")


class TestTokenProperties:
    """Test Token helper properties."""

    def test_is_keyword(self):
        t = Token(TokenType.KEYWORD, "SELECT")
        assert t.is_keyword

    def test_is_identifier(self):
        t = Token(TokenType.IDENTIFIER, "users")
        assert t.is_identifier

    def test_is_literal_integer(self):
        t = Token(TokenType.INTEGER, "42")
        assert t.is_literal

    def test_is_literal_string(self):
        t = Token(TokenType.STRING, "hello")
        assert t.is_literal

    def test_keyword_is(self):
        t = Token(TokenType.KEYWORD, "SELECT")
        assert t.keyword_is("SELECT")
        assert t.keyword_is("select")

    def test_keyword_is_not(self):
        t = Token(TokenType.KEYWORD, "SELECT")
        assert not t.keyword_is("INSERT")
