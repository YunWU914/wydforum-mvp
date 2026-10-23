#!/usr/bin/env python
"""One-off migration: import legacy forum_project data into the community app.

Usage:
    python tools/import_legacy.py <path/to/legacy/db.sqlite3> [path/to/target/db.sqlite3]

- Copies users (keeping password hashes), skipping usernames that already exist.
- Copies categories (name -> zh_hans, name_en -> en) into the i18n JSON fields.
- Copies posts as topics (status "approved" -> visible, others hidden).
- Idempotent-ish: skips users/categories already present by username/slug;
  topics are only imported when the target has no legacy topics yet
  (legacy topics are detected by title match against imported titles).
"""

import json
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = BASE_DIR / "data" / "db.sqlite3"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    legacy_path = Path(sys.argv[1])
    target_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_TARGET
    if not legacy_path.is_file():
        print(f"legacy db not found: {legacy_path}")
        return 2
    if not target_path.is_file():
        print(f"target db not found: {target_path}")
        return 2

    con = sqlite3.connect(target_path)
    con.row_factory = sqlite3.Row
    con.execute("ATTACH DATABASE ? AS old", (str(legacy_path),))
    cur = con.cursor()  # inner/single-statement cursor
    outer = con.cursor()  # iteration cursor (kept separate from inner queries)

    # --- users -------------------------------------------------------------
    existing_usernames = {
        r["username"] for r in cur.execute("SELECT username FROM auth_user")
    }
    user_map: dict[int, int] = {}  # legacy id -> target id
    for u in outer.execute(
        "SELECT id, username, password, last_login, is_superuser, first_name,"
        " last_name, email, is_staff, is_active, date_joined FROM old.auth_user"
    ):
        if u["username"] in existing_usernames:
            row = cur.execute(
                "SELECT id FROM auth_user WHERE username = ?", (u["username"],)
            ).fetchone()
            user_map[u["id"]] = row["id"]
            print(f"user skipped (exists): {u['username']} -> id {row['id']}")
            continue
        cur.execute(
            "INSERT INTO auth_user (password, last_login, is_superuser, username,"
            " first_name, last_name, email, is_staff, is_active, date_joined)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                u["password"], u["last_login"], u["is_superuser"], u["username"],
                u["first_name"], u["last_name"], u["email"], u["is_staff"],
                u["is_active"], u["date_joined"],
            ),
        )
        new_id = cur.lastrowid
        user_map[u["id"]] = new_id
        cur.execute(
            "INSERT INTO community_profile (email_verified, bio, created_at, user_id)"
            " VALUES (1, '', ?, ?)",
            (u["date_joined"], new_id),
        )
        print(f"user imported: {u['username']} (old {u['id']} -> new {new_id})")

    # --- categories ----------------------------------------------------------
    existing_slugs = {
        r["slug"] for r in cur.execute("SELECT slug FROM community_category")
    }
    cat_map: dict[int, int] = {}  # legacy id -> target id
    for c in outer.execute(
        "SELECT id, name, slug, description, name_en, is_active,"
        " COALESCE(\"order\", id * 10) AS pos FROM old.forum_category ORDER BY id"
    ):
        if c["slug"] in existing_slugs:
            row = cur.execute(
                "SELECT id FROM community_category WHERE slug = ?", (c["slug"],)
            ).fetchone()
            cat_map[c["id"]] = row["id"]
            print(f"category skipped (exists): {c['slug']}")
            continue
        names = {"zh_hans": c["name"], "en": c["name_en"] or c["name"]}
        descriptions = (
            {"zh_hans": c["description"], "en": c["description"]}
            if c["description"] else {}
        )
        cur.execute(
            "INSERT INTO community_category (slug, names, descriptions, position,"
            " is_active) VALUES (?,?,?,?,?)",
            (
                c["slug"], json.dumps(names, ensure_ascii=False),
                json.dumps(descriptions, ensure_ascii=False), c["pos"],
                1 if c["is_active"] else 0,
            ),
        )
        cat_map[c["id"]] = cur.lastrowid
        print(f"category imported: {c['slug']} (old {c['id']} -> new {cur.lastrowid})")

    # --- topics ---------------------------------------------------------------
    imported_titles = {
        r[0]
        for r in cur.execute(
            "SELECT title FROM community_topic"
            " WHERE title IN (SELECT title FROM old.forum_post)"
        )
    }
    topics = 0
    for p in outer.execute(
        "SELECT id, title, content, created_at, updated_at, is_pinned, views,"
        " status, author_id, category_id FROM old.forum_post ORDER BY id"
    ):
        if p["title"] in imported_titles:
            print(f"topic skipped (already imported): {p['title'][:50]}")
            continue
        author_id = user_map.get(p["author_id"])
        category_id = cat_map.get(p["category_id"])
        if not author_id or not category_id:
            print(f"topic skipped (no author/category mapping): {p['title'][:50]}")
            continue
        cur.execute(
            "INSERT INTO community_topic (title, body, created_at, updated_at,"
            " last_activity_at, is_pinned, is_locked, is_hidden, views, author_id,"
            " category_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                p["title"][:200], p["content"], p["created_at"], p["updated_at"],
                p["created_at"], 1 if p["is_pinned"] else 0, 0,
                0 if p["status"] == "approved" else 1, p["views"] or 0,
                author_id, category_id,
            ),
        )
        topics += 1
    print(f"topics imported: {topics}")

    con.commit()
    con.close()
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
