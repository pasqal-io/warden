"""Portable SQL expressions.

Warden supports SQLite, PostgreSQL and MariaDB, which do not share a way to
express an elapsed duration between two datetime columns. These helpers compile
to the right expression per dialect.
"""

from sqlalchemy import Integer, cast, func, text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import FunctionElement


class duration_seconds(FunctionElement):
    """Whole seconds elapsed between two datetime columns, rounded to the
    nearest second and returned as an integer.

    Usage: ``duration_seconds(started_at, ended_at)``. NULL on either side
    yields NULL, so it composes with ``func.sum`` the usual way.

    Rounding (rather than truncation) keeps the value robust to the sub-second
    float error julianday() introduces on SQLite -- an exact hour must not come
    back as 3599. The instance-level hybrids use round() to match. (Switching
    both sides to int()-style truncation is deferred; see the models.)
    """

    type = Integer()
    inherit_cache = True
    name = "duration_seconds"


@compiles(duration_seconds, "postgresql")
def _duration_seconds_postgresql(element, compiler, **kw):
    # extract(epoch, ...) yields double precision; round and cast so the
    # result is an integer count of seconds, not a float.
    start, end = list(element.clauses)
    seconds = func.extract("epoch", end - start)
    return compiler.process(cast(func.round(seconds), Integer), **kw)


@compiles(duration_seconds, "sqlite")
def _duration_seconds_sqlite(element, compiler, **kw):
    # SQLite has no interval type: subtracting datetimes coerces them to
    # numbers. julianday() gives fractional days, which we scale to seconds.
    # The scaling is lossy in binary float (an exact hour comes back as
    # 3599.999...), so round to the nearest whole second before casting to
    # INTEGER -- a bare cast would truncate 3599.999... down to 3599.
    start, end = list(element.clauses)
    seconds = (func.julianday(end) - func.julianday(start)) * 86400.0
    return compiler.process(cast(func.round(seconds), Integer), **kw)


@compiles(duration_seconds, "mysql")
def _duration_seconds_mysql(element, compiler, **kw):
    # MariaDB is served by the mysql dialect; EXTRACT has no epoch unit here.
    # DATETIME columns store whole seconds (fsp=0), so TIMESTAMPDIFF(SECOND, ...)
    # already yields the same integer as rounding to the nearest second.
    start, end = list(element.clauses)
    return compiler.process(func.timestampdiff(text("SECOND"), start, end), **kw)


@compiles(duration_seconds)
def _duration_seconds_default(element, compiler, **kw):
    raise NotImplementedError(
        f"duration_seconds() is not implemented for dialect {compiler.dialect.name!r}."
    )
