import json
from pathlib import Path
from uuid import uuid4

import typer
from tomledit import Document

app = typer.Typer()
authors_app = typer.Typer()
app.add_typer(authors_app, name="authors")


@app.command("add-uuid")
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


@authors_app.command("add-category")
def add_category_to_authors():
    with open("./categories.json", "r") as f:
        data = json.load(f)
        for author in data:
            file = Path(author["name"], "metadata.toml")
            metadata = Document.parse(file.read_text(encoding="utf-8"))
            if "category" not in metadata.keys():
                metadata["category"] = author["category"]
                _ = file.write_text(metadata.as_toml(), encoding="utf-8")


@authors_app.command("missing-category")
def find_authors_with_category():
    target_dir = Path(".")
    for path in target_dir.rglob("metadata.toml"):
        data = Document.parse(path.read_text(encoding="utf-8"))
        if "category" not in data.keys():
            print(data)


def main():
    app()


if __name__ == "__main__":
    main()
