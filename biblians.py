import json
import os
from enum import Enum
from pathlib import Path
from time import sleep
from uuid import uuid4

import requests
import typer
from dotenv import load_dotenv
from rich.progress import Progress
from tomledit import Document

app = typer.Typer()
authors_app = typer.Typer()
app.add_typer(authors_app, name="authors")


class MetadataType(str, Enum):
    image = "image"
    summary = "summary"
    both = "both"


@app.command("add-uuid")
def add_uuid():
    target_dir = Path(".")
    for path in target_dir.rglob("*.toml"):
        data = Document.parse(path.read_text(encoding="utf-8"))
        if "commentary" in data:
            file_changed = False
            for commentary in data["commentary"]:
                if "uuid" not in commentary:
                    commentary["uuid"] = str(uuid4())
                    file_changed = True
            if file_changed:
                _ = path.write_text(data.as_toml(), encoding="utf-8")
        elif "wiki" in data:
            if "uuid" not in data:
                data["uuid"] = str(uuid4())
                _ = path.write_text(data.as_toml(), encoding="utf-8")


@authors_app.command("add-category")
def add_category_to_authors():
    with open("./categories.json", "r") as f:
        data = json.load(f)
        for author in data:
            file = Path(author["name"], "metadata.toml")
            metadata = Document.parse(file.read_text(encoding="utf-8"))
            if "category" not in metadata:
                metadata["category"] = author["category"]
                _ = file.write_text(metadata.as_toml(), encoding="utf-8")


@authors_app.command("missing-category")
def find_authors_with_category():
    target_dir = Path(".")
    for path in target_dir.rglob("metadata.toml"):
        data = Document.parse(path.read_text(encoding="utf-8"))
        if "category" not in data:
            print(data)


@authors_app.command("add-metadata")
def add_metadata_to_authors():
    user_agent = os.getenv("USER_AGENT", None)
    if user_agent is None:
        raise Exception("USER_AGENT environment variable is not set")
    headers = {"User-Agent": os.getenv("USER_AGENT")}

    target_dir = Path(".")
    with Progress() as progress:
        task_id = progress.add_task(f"Processing authors...", total=None)
        count = 0
        for path in target_dir.rglob("metadata.toml"):
            data = Document.parse(path.read_text(encoding="utf-8"))
            wiki = data["wiki"]
            summary = data.get("summary", None)
            image = data.get("image", None)
            if "wikipedia.org" in wiki and (summary is None or image is None):
                id = wiki.split("/")[-1]
                url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{id}"
                resp = requests.get(url, headers=headers)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                wiki_data = resp.json()

                image = wiki_data.get("originalimage", None)
                if image is not None:
                    data["image"] = image["source"]
                summary = wiki_data.get("extract", None)
                if summary is not None:
                    data["summary"] = summary.strip()
                _ = path.write_text(data.as_toml(), encoding="utf-8")

                count += 1
                progress.update(
                    task_id,
                    advance=1,
                    description=f"Processed {id} ({count} items)",
                )
                sleep(0.3)


@authors_app.command("missing-metadata")
def find_authors_with_missing_metadata(
    type: MetadataType = MetadataType.both,
):
    target_dir = Path(".")
    for path in target_dir.rglob("metadata.toml"):
        data = Document.parse(path.read_text(encoding="utf-8"))
        missing = [field for field in ("image", "summary") if field not in data]

        if not missing:
            continue

        if type != MetadataType.both:
            if type.value not in missing:
                continue

            print(f"{path.parent.name} is missing {type.value}")
            print(data)
            print()
            continue

        print(f"{path.parent.name} is missing the following metadata:")
        for field in missing:
            print(f"- {field}")
        print(data)
        print()


def main():
    _ = load_dotenv()
    app()


if __name__ == "__main__":
    main()
