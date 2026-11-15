#!/usr/bin/env python3
"""SQL 表名/别名抽取验收探针。

契约：
  from sqlparse.tables import extract
  res = extract(sql)
  res.statement_type  小写语句类型，如 "select" / "insert" / "update"
  res.tables          列表，每项含 .name / .alias / .schema（无则为空串），按出现顺序
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FAILED = 0
PASSED = 0


def check(code, desc, fn):
    global FAILED, PASSED
    try:
        fn()
        print(f"[PASS] {code} {desc}")
        PASSED += 1
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {code} {desc}")
        print(f"        {type(exc).__name__}: {exc}")
        FAILED += 1


def main():
    try:
        from sqlparse.tables import extract  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] P0 导入 sqlparse.tables 失败：{type(exc).__name__}: {exc}")
        print("-" * 60)
        print("探针汇总：0/6 通过")
        return 1

    def p1():
        r = extract("SELECT id FROM orders")
        assert r.statement_type == "select", r.statement_type
        assert [t.name for t in r.tables] == ["orders"], [t.name for t in r.tables]

    def p2():
        r = extract("SELECT a.id FROM orders a JOIN users u ON a.uid = u.id")
        pairs = {(t.name, t.alias) for t in r.tables}
        assert pairs == {("orders", "a"), ("users", "u")}, pairs

    def p3():
        r = extract("SELECT * FROM s1.orders")
        assert r.tables[0].schema == "s1", r.tables[0].schema
        assert r.tables[0].name == "orders"

    def p4():
        r = extract("WITH recent AS (SELECT * FROM logs) SELECT * FROM recent")
        names = [t.name for t in r.tables]
        assert "logs" in names, names
        assert "recent" not in names, names

    def p5():
        a = extract("INSERT INTO orders (id) VALUES (1)")
        b = extract("UPDATE users SET x = 1")
        assert a.statement_type == "insert", a.statement_type
        assert [t.name for t in a.tables] == ["orders"]
        assert b.statement_type == "update", b.statement_type
        assert [t.name for t in b.tables] == ["users"]

    def p6():
        r = extract("SELECT 1")
        assert r.tables == [], [t.name for t in r.tables]
        import sqlparse
        assert sqlparse.format("select 1", reindent=True) is not None

    check("P1", "单表 SELECT", p1)
    check("P2", "JOIN 与别名", p2)
    check("P3", "带库名限定", p3)
    check("P4", "CTE 名不计入表", p4)
    check("P5", "INSERT / UPDATE 语句类型", p5)
    check("P6", "无表语句与既有 format 不变", p6)

    print("-" * 60)
    print(f"探针汇总：{PASSED}/{PASSED + FAILED} 通过")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
