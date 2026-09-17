"""TDD-009: Smart Rules & Virtual Collections.

A VirtualCollection is a saved rule set that filters the library without
moving or copying any files -- it compiles to a parameterized SQL WHERE
clause that DatabaseManager.query_documents() runs alongside (or instead
of) a text search.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field

# Columns that also exist on documents_fts; a rule targeting one of these
# must be qualified as documents.<col> so it stays unambiguous when a text
# search is combined with the collection filter (see DatabaseManager.query_documents).
_FTS_SHARED_COLUMNS = {"title", "author", "tags", "content"}

_ALLOWED_FIELDS = {"title", "author", "extension", "tags", "file_size", "created_at"}

_OPERATOR_SQL = {
    "eq": "=",
    "gt": ">",
    "lt": "<",
    "contains": "LIKE",
}


@dataclass(frozen=True)
class SmartRule:
    field: str
    operator: str  # "eq" | "gt" | "lt" | "contains"
    value: str

    def __post_init__(self) -> None:
        if self.field not in _ALLOWED_FIELDS:
            raise ValueError(f"Unknown field for a Smart Rule: {self.field!r}")
        if self.operator not in _OPERATOR_SQL:
            raise ValueError(f"Unknown operator for a Smart Rule: {self.operator!r}")

    def to_sql(self) -> tuple[str, str]:
        """Returns (sql_fragment, parameter) -- never interpolates `value`."""
        column = f"documents.{self.field}" if self.field in _FTS_SHARED_COLUMNS else self.field
        if self.operator == "contains":
            return f"{column} LIKE ?", f"%{self.value}%"
        return f"{column} {_OPERATOR_SQL[self.operator]} ?", self.value


@dataclass
class VirtualCollection:
    name: str
    rules: list[SmartRule] = field(default_factory=list)
    logic: str = "AND"  # "AND" | "OR"
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.logic not in ("AND", "OR"):
            raise ValueError(f"logic must be 'AND' or 'OR', got {self.logic!r}")

    def to_sql_where_clause(self) -> tuple[str, tuple]:
        if not self.rules:
            return "1=1", ()
        fragments: list[str] = []
        params: list = []
        for rule in self.rules:
            fragment, value = rule.to_sql()
            fragments.append(fragment)
            params.append(value)
        joiner = f" {self.logic} "
        return joiner.join(fragments), tuple(params)

    def to_json(self) -> str:
        return json.dumps(
            {
                "rules": [{"field": r.field, "operator": r.operator, "value": r.value} for r in self.rules],
            }
        )

    @classmethod
    def from_row(cls, row: dict) -> "VirtualCollection":
        payload = json.loads(row["rules_json"])
        rules = [SmartRule(**r) for r in payload["rules"]]
        return cls(
            name=row["name"],
            rules=rules,
            logic=row["logic"],
            id=row["id"],
            created_at=row["created_at"],
        )


if __name__ == "__main__":
    collection = VirtualCollection(
        name="Sach AI moi",
        rules=[
            SmartRule(field="created_at", operator="gt", value="1700000000"),
            SmartRule(field="tags", operator="contains", value="AI"),
        ],
        logic="AND",
    )
    where_sql, params = collection.to_sql_where_clause()
    print("WHERE:", where_sql)
    print("params:", params)
    assert where_sql == "created_at > ? AND documents.tags LIKE ?"
    assert params == ("1700000000", "%AI%")

    round_tripped = VirtualCollection.from_row(
        {"id": collection.id, "name": collection.name, "rules_json": collection.to_json(), "logic": collection.logic, "created_at": collection.created_at}
    )
    assert round_tripped.to_sql_where_clause() == (where_sql, params)
    print("round-trip OK")
