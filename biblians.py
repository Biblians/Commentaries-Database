import argparse
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from tomledit import Document


@dataclass
class Args:
    add_uuid: bool = False


def parse_arguments() -> Args:
    parser = argparse.ArgumentParser(
        prog="Biblians",
    )

    parser.add_argument(
        "--add-uuid",
        action="store_true",
        help="add uuid to toml files (authors and verses)",
    )
    return parser.parse_args(namespace=Args())


def add_uuid():
    target_dir = Path(".")
    for path in target_dir.rglob("*.toml"):
        data = Document.parse(path.read_text(encoding="utf-8"))
        if "commentary" in data.keys():
            file_changed = False
            for idx, _ in enumerate(data["commentary"]):
                commentary = data["commentary"][idx]
                if "uuid" not in commentary.keys():
                    commentary["uuid"] = str(uuid4())
                    file_changed = True
            if file_changed:
                _ = path.write_text(data.as_toml(), encoding="utf-8")
        elif "wiki" in data.keys():
            if "uuid" not in data.keys():
                data["uuid"] = str(uuid4())
                _ = path.write_text(data.as_toml(), encoding="utf-8")


def main():
    args = parse_arguments()
    if args.add_uuid:
        add_uuid()


if __name__ == "__main__":
    main()
