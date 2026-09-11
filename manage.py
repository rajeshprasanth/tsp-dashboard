#!/usr/bin/env python3
"""User management for the dashboard.

Passwords are stored as salted PBKDF2 hashes (werkzeug), never in
plaintext. Example usage::

    python3 manage.py add-user --username admin --password 'hunter2' --role admin
    python3 manage.py add-user --username viewer --password 'secrets' --role viewer
    python3 manage.py list-users
    python3 manage.py remove-user --username viewer

Users are stored in the file pointed to by ``TSPD_USERS_FILE`` (default:
``users.json``); the dashboard reads users from that file only.
"""

import argparse
import json
import sys
from pathlib import Path

from werkzeug.security import generate_password_hash

ROLES = ("admin", "viewer")


def _load(path):
    if path.exists():
        try:
            data = json.loads(path.read_text() or "{}")
            return data if isinstance(data, dict) else {}
        except ValueError as exc:
            print(f"warning: {path} is not valid JSON ({exc}); starting fresh", file=sys.stderr)
    return {}


def _save(path, users):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(users, indent=2) + "\n")


def cmd_add_user(args):
    path = Path(args.file)
    users = _load(path)
    if args.username in users and not args.force:
        print(
            f"error: user '{args.username}' already exists "
            f"(use --force to overwrite)",
            file=sys.stderr,
        )
        sys.exit(1)
    users[args.username] = {
        "role": args.role,
        "password": generate_password_hash(args.password),
    }
    _save(path, users)
    print(f"user '{args.username}' ({args.role}) written to {path}")


def cmd_list_users(args):
    path = Path(args.file)
    users = _load(path)
    if not users:
        print("no users configured")
        return
    for name, spec in sorted(users.items()):
        role = spec.get("role", "viewer")
        has_pw = "set" if spec.get("password") else "MISSING"
        print(f"{name:<20} {role:<8} (password {has_pw})")


def cmd_remove_user(args):
    path = Path(args.file)
    users = _load(path)
    if args.username not in users:
        print(f"user '{args.username}' not found", file=sys.stderr)
        sys.exit(1)
    del users[args.username]
    _save(path, users)
    print(f"removed user '{args.username}'")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="manage.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--file", default="users.json", help="users file (default: users.json)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add-user", help="create or update a user")
    p_add.add_argument("--username", required=True)
    p_add.add_argument("--password", required=True)
    p_add.add_argument("--role", default="viewer", choices=ROLES)
    p_add.add_argument("--force", action="store_true", help="overwrite an existing user")
    p_add.set_defaults(func=cmd_add_user)

    p_list = sub.add_parser("list-users", help="list configured users")
    p_list.set_defaults(func=cmd_list_users)

    p_rm = sub.add_parser("remove-user", help="remove a user")
    p_rm.add_argument("--username", required=True)
    p_rm.set_defaults(func=cmd_remove_user)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()