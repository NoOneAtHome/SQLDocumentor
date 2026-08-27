"""Pure helpers in the catalog extractor: SQL loading, type display, kind mapping."""

import pytest

from sqldoc.mssql.catalog import QUERY_NAMES, load_sql, object_kind, type_display


def test_every_query_file_loads_and_targets_sys_views():
    assert {"objects", "columns", "dependencies", "modules", "table_stats"} <= set(QUERY_NAMES)
    for name in QUERY_NAMES:
        sql = load_sql(name)
        assert "SELECT" in sql.upper(), name


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (dict(type_name="int"), "int"),
        (dict(type_name="bigint", max_length=8, precision=19), "bigint"),
        (dict(type_name="nvarchar", max_length=100), "nvarchar(50)"),
        (dict(type_name="nvarchar", max_length=-1), "nvarchar(max)"),
        (dict(type_name="nchar", max_length=20), "nchar(10)"),
        (dict(type_name="varchar", max_length=20), "varchar(20)"),
        (dict(type_name="varchar", max_length=-1), "varchar(max)"),
        (dict(type_name="char", max_length=10), "char(10)"),
        (dict(type_name="binary", max_length=16), "binary(16)"),
        (dict(type_name="varbinary", max_length=-1), "varbinary(max)"),
        (dict(type_name="decimal", max_length=9, precision=18, scale=2), "decimal(18,2)"),
        (dict(type_name="numeric", max_length=9, precision=10, scale=0), "numeric(10,0)"),
        (dict(type_name="datetime2", max_length=8, precision=27, scale=7), "datetime2(7)"),
        (dict(type_name="time", max_length=5, precision=16, scale=7), "time(7)"),
        (
            dict(type_name="datetimeoffset", max_length=10, precision=34, scale=7),
            "datetimeoffset(7)",
        ),
        (dict(type_name="float", max_length=8, precision=53), "float"),
        (dict(type_name="xml"), "xml"),
        (dict(type_name="sysname", max_length=256), "sysname"),
        (
            dict(
                type_name="Name", is_user_defined=True, system_type_name="nvarchar", max_length=100
            ),
            "Name",
        ),
    ],
)
def test_type_display(args, expected):
    assert type_display(**args) == expected


@pytest.mark.parametrize(
    ("code", "kind"),
    [
        ("U", "table"),
        ("V", "view"),
        ("P", "procedure"),
        ("PC", "procedure"),
        ("FN", "scalar_function"),
        ("IF", "inline_tvf"),
        ("TF", "table_function"),
        ("FS", "clr_function"),
        ("FT", "clr_function"),
        ("TR", "trigger"),
        ("TA", "trigger"),
        ("SN", "synonym"),
        ("SO", "sequence"),
        ("TT", "table_type"),
    ],
)
def test_object_kind(code, kind):
    assert object_kind(code) == kind


def test_object_kind_unknown():
    assert object_kind("ZZ") is None
    assert object_kind("U ") == "table"  # sys.objects.type is char(2), padded
