"""Multipart name parsing and stable identity keys."""

import pytest

from sqldoc.mssql.identity import (
    ObjectRef,
    column_key,
    external_key,
    object_key,
    parse_multipart_name,
    temp_key,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Person", ObjectRef(None, None, None, "Person")),
        ("Person.Person", ObjectRef(None, None, "Person", "Person")),
        ("[Sales].[Customer]", ObjectRef(None, None, "Sales", "Customer")),
        ('"Sales"."Customer"', ObjectRef(None, None, "Sales", "Customer")),
        (
            "AdventureWorks2022.Sales.Customer",
            ObjectRef(None, "AdventureWorks2022", "Sales", "Customer"),
        ),
        ("srv.db.dbo.t", ObjectRef("srv", "db", "dbo", "t")),
        ("db..t", ObjectRef(None, "db", None, "t")),
        ("[my.table]", ObjectRef(None, None, None, "my.table")),
        ("[we]]ird].[x]", ObjectRef(None, None, "we]ird", "x")),
        ("#temp", ObjectRef(None, None, None, "#temp")),
        ("  dbo . Thing  ", ObjectRef(None, None, "dbo", "Thing")),
    ],
)
def test_parse_multipart_name(text, expected):
    assert parse_multipart_name(text) == expected


def test_parse_rejects_more_than_four_parts():
    with pytest.raises(ValueError):
        parse_multipart_name("a.b.c.d.e")


def test_parse_rejects_empty():
    with pytest.raises(ValueError):
        parse_multipart_name("")


def test_keys():
    ok = object_key("local-aw", "AW", "Sales", "Customer")
    assert ok == "local-aw|AW|Sales|Customer"
    assert column_key(ok, "Name") == "local-aw|AW|Sales|Customer|Name"
    assert external_key(None, "OtherDb", "dbo", "T") == "external||OtherDb|dbo|T"
    assert external_key("srv", "OtherDb", None, "T") == "external|srv|OtherDb||T"
    assert temp_key(ok, "t") == "local-aw|AW|Sales|Customer|#t"


def test_object_ref_display_and_case_insensitive_matching():
    ref = parse_multipart_name("Sales.Customer")
    assert ref.display() == "Sales.Customer"
    assert parse_multipart_name("db.Sales.Customer").display() == "db.Sales.Customer"
    assert ref.matches(schema="SALES", name="customer")
    assert not ref.matches(schema="Sales", name="Other")
