#
# Copyright (C) 2009-2020 the sqlparse authors and contributors
# <see AUTHORS file>
#
# This module is part of python-sqlparse and is released under
# the BSD License: https://opensource.org/licenses/BSD-3-Clause

"""Extract table names, aliases and schema qualifiers from SQL statements.

The public entry point is :func:`extract`, which takes a SQL string and
returns an :class:`ExtractionResult`.  Only the token tree produced by
:func:`sqlparse.parse` is used; no additional dependencies are required.
"""

from sqlparse import parse
from sqlparse import tokens as T
from sqlparse.sql import Comment, Function, Identifier, IdentifierList, Parenthesis

# Keywords that introduce a table reference.  JOIN variants are matched by
# suffix, so plain JOIN / LEFT JOIN / FULL OUTER JOIN / ... all qualify.
_TABLE_KEYWORDS = ('FROM', 'INTO', 'UPDATE')


class Table:
    """A table reference found in a statement."""

    __slots__ = ('alias', 'name', 'schema')

    def __init__(self, name, alias='', schema=''):
        self.name = name
        self.alias = alias
        self.schema = schema

    def __eq__(self, other):
        if not isinstance(other, Table):
            return NotImplemented
        return (self.name == other.name
                and self.alias == other.alias
                and self.schema == other.schema)

    def __repr__(self):
        return (f'Table(name={self.name!r}, alias={self.alias!r}, '
                f'schema={self.schema!r})')


class ExtractionResult:
    """Result of :func:`extract` for a single statement."""

    __slots__ = ('statement_type', 'tables')

    def __init__(self, statement_type, tables):
        self.statement_type = statement_type
        self.tables = tables

    def __repr__(self):
        return (f'ExtractionResult(statement_type={self.statement_type!r}, '
                f'tables={self.tables!r})')


def _is_table_keyword(token):
    if not token.is_keyword:
        return False
    normalized = token.normalized.upper()
    return normalized in _TABLE_KEYWORDS or normalized.endswith('JOIN')


def _is_cte_definition(identifier):
    # A CTE definition looks like "name AS (subquery)"; a derived table is
    # "(subquery) alias" and therefore has no AS keyword.
    if identifier.token_next_by(m=(T.Keyword, 'AS'))[1] is None:
        return False
    return identifier.token_next_by(i=Parenthesis)[1] is not None


def _collect_cte_names(group, names):
    # Check the group itself before descending into its children: when the
    # caller recurses into an Identifier its own tokens are plain leaves.
    if isinstance(group, Identifier):
        if _is_cte_definition(group):
            name = group.get_real_name()
            if name:
                names.add(name)
        # CTEs may be nested inside the defining subquery.
        _, parenthesis = group.token_next_by(i=Parenthesis)
        if parenthesis is not None:
            _collect_cte_names(parenthesis, names)
        return

    for token in group.tokens:
        if isinstance(token, IdentifierList):
            for item in token.get_identifiers():
                _collect_cte_names(item, names)
        elif token.is_group:
            _collect_cte_names(token, names)


def _add_identifier_table(identifier, cte_names, tables):
    name = identifier.get_real_name()
    if not name or name in cte_names:
        return
    tables.append(Table(
        name=name,
        alias=identifier.get_alias() or '',
        schema=identifier.get_parent_name() or '',
    ))


def _walk(group, expect_table, cte_names, tables):
    for token in group.tokens:
        if token.is_whitespace or isinstance(token, Comment) \
                or (token.ttype is not None and token.ttype in T.Comment):
            continue

        if isinstance(token, IdentifierList):
            for item in token.get_identifiers():
                _handle_table_position_token(item, expect_table,
                                             cte_names, tables)
            continue

        if isinstance(token, Identifier):
            _handle_table_position_token(token, expect_table,
                                         cte_names, tables)
            continue

        if isinstance(token, Function):
            # INSERT without a schema qualifier groups the target as a
            # Function, e.g. "INSERT INTO orders (id) ...".  The Function's
            # first name token is the target table; get_alias() is not used
            # because a bare function name reads back as its own "alias".
            if expect_table:
                name = token.get_real_name()
                if name and name not in cte_names:
                    tables.append(Table(name=name))
            _walk(token, False, cte_names, tables)
            continue

        if _is_table_keyword(token):
            expect_table = True
            continue

        if token.is_group:
            # Parenthesized subqueries restart the keyword scan on their own;
            # every other group (WHERE, comparisons, ...) holds columns.
            _walk(token, False, cte_names, tables)
            continue
        # Plain leaf tokens (literals, punctuation, ...) carry no tables.


def _handle_table_position_token(token, expect_table, cte_names, tables):
    if not isinstance(token, Identifier):
        if isinstance(token, Function) and expect_table:
            name = token.get_real_name()
            if name and name not in cte_names:
                tables.append(Table(name=name))
        if token.is_group:
            _walk(token, False, cte_names, tables)
        return

    _, parenthesis = token.token_next_by(i=Parenthesis)
    if parenthesis is not None:
        # CTE definition or derived table: the name/alias is not a real
        # table, but the underlying tables inside the subquery are.
        _walk(parenthesis, False, cte_names, tables)
        return

    if expect_table:
        _add_identifier_table(token, cte_names, tables)


def extract(sql):
    """Extract table references from the first statement in *sql*.

    Returns an :class:`ExtractionResult` whose ``statement_type`` is the
    lower-cased statement type (e.g. ``"select"``) and whose ``tables`` is
    a list of :class:`Table` items in order of appearance.  CTE names are
    excluded while the tables referenced inside CTE bodies are included.
    Statements without tables yield an empty list instead of raising.
    """
    statements = parse(sql)
    if not statements:
        return ExtractionResult('', [])

    statement = statements[0]
    statement_type = statement.get_type()
    statement_type = statement_type.lower() if statement_type else ''

    cte_names = set()
    _collect_cte_names(statement, cte_names)

    tables = []
    _walk(statement, False, cte_names, tables)
    return ExtractionResult(statement_type, tables)
