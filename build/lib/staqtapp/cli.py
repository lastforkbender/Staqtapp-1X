from __future__ import annotations

import argparse
import json
from pathlib import Path

import staqtapp


def _print(value):
    if value is not None:
        print(json.dumps(value, indent=2, default=str) if isinstance(value, (dict, list)) else value)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="staqtapp", description="Staqtapp 1.4 SQTPP tools")
    parser.add_argument("--home", help="storage directory (also supported through STAQTAPP_HOME)")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="create and select a VFS")
    create.add_argument("name"); create.add_argument("directory"); create.add_argument("folder")
    select = sub.add_parser("select", help="select an existing VFS")
    select.add_argument("name"); select.add_argument("directory"); select.add_argument("folder")
    sub.add_parser("info", help="show selected VFS metadata")
    sub.add_parser("list", help="list variables")
    verify = sub.add_parser("verify", help="verify an SQTPP file")
    verify.add_argument("path", nargs="?"); verify.add_argument("--directory"); verify.add_argument("--folder")
    migrate = sub.add_parser("migrate", help="copy/canonicalize without modifying the source")
    migrate.add_argument("source"); migrate.add_argument("destination"); migrate.add_argument("directory"); migrate.add_argument("folder")
    migrate.add_argument("--report")
    sub.add_parser("recover", help="restore the selected VFS from its last transaction backup")

    args = parser.parse_args(argv)
    if args.home: staqtapp.configure(storage_dir=args.home)
    if args.command == "create": staqtapp.makevfs(args.name, args.directory, args.folder)
    elif args.command == "select": staqtapp.setpath(args.name, args.directory, args.folder)
    elif args.command == "info": _print(staqtapp.listfiles())
    elif args.command == "list": _print(staqtapp.listvars())
    elif args.command == "verify": _print(staqtapp.verify_vfs(args.path, args.directory, args.folder))
    elif args.command == "migrate": _print(staqtapp.migrate_vfs(args.source, args.destination, args.directory, args.folder, report_path=args.report))
    elif args.command == "recover": staqtapp.recover_vfs()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
