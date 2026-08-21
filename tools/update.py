import argparse
import json
import shutil
import zipfile
from pathlib import Path
from datetime import datetime

def load_manifest(package):
    with zipfile.ZipFile(package) as z:
        return json.loads(z.read("manifest.json"))

def install(package, root=".", dry_run=False):
    root = Path(root).resolve()
    manifest = load_manifest(package)

    print("RLW Update")
    print("Version:", manifest.get("version"))
    print()

    with zipfile.ZipFile(package) as z:
        files = [f for f in z.namelist() if f.startswith("payload/")]

        for f in files:
            target = root / f[len("payload/"):]
            print(("[DRY] " if dry_run else "") + str(target))

        if dry_run:
            return

        backup = (
            root /
            ".rlw_updates" /
            datetime.now().strftime("%Y%m%d_%H%M%S") /
            "backup"
        )

        backup.mkdir(parents=True, exist_ok=True)

        for f in files:
            target = root / f[len("payload/"):]

            if target.exists():
                shutil.copy2(
                    target,
                    backup / target.name
                )

            target.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            with z.open(f) as src:
                target.write_bytes(src.read())

    print("RLW update finished.")

def main():
    parser = argparse.ArgumentParser(
        description="RLW update manager"
    )

    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("install")
    p.add_argument("package")
    p.add_argument("--root", default=".")
    p.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.command == "install":
        install(
            args.package,
            args.root,
            args.dry_run
        )

if __name__ == "__main__":
    main()
