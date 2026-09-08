import hashlib
import json
import os
import re
import subprocess
import tempfile
from enum import Enum
from pathlib import Path
from time import sleep
from urllib.parse import unquote, urlparse
from uuid import uuid4

import requests
import typer
from dotenv import load_dotenv
from pydantic import BaseModel
from rich.progress import Progress
from tomledit import Document
from unidecode import unidecode

from compile_data import encode_chapter_verse, string_to_verse_range
from constants import name_to_osis

app = typer.Typer()
authors_app = typer.Typer()
convert_app = typer.Typer()
app.add_typer(authors_app, name="authors")
app.add_typer(convert_app, name="convert")


class MetadataType(str, Enum):
    image = "image"
    summary = "summary"
    category = "category"
    both = "both"


class Commentary(BaseModel):
    id: str
    quote: str
    source_title: str | None
    source_url: str | None
    append_to_author_name: str | None
    time: int
    location_start: int
    location_end: int
    chapter_start: int
    chapter_end: int
    osisId: str
    display_reference: str


class Author(BaseModel):
    uuid: str
    name: str
    death_year: int
    category: str
    wiki: str | None
    image: str | None
    summary: str | None
    commentaries: list[Commentary]


# Author Commands
@authors_app.command("add-uuid")
def add_uuid():
    target_dir = Path(".")
    for path in target_dir.rglob("*.toml"):
        data = Document.parse(path.read_text(encoding="utf-8"))
        if "wiki" in data:
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
    IMAGE_PATH = os.getenv("IMAGE_PATH", None)
    if IMAGE_PATH is None:
        raise Exception("IMAGE_PATH environment variable is not set")
    USER_AGENT = os.getenv("USER_AGENT", None)
    if USER_AGENT is None:
        raise Exception("USER_AGENT environment variable is not set")
    headers = {"User-Agent": USER_AGENT}

    target_dir = Path(".")
    with Progress() as progress:
        task_id = progress.add_task("Processing authors...", total=None)
        count = 0
        for path in target_dir.rglob("metadata.toml"):
            data = Document.parse(path.read_text(encoding="utf-8"))
            wiki = data["wiki"]
            doc_summary = data.get("summary", None)
            doc_image = data.get("image", None)
            if "wikipedia.org" in wiki and (doc_summary is None or doc_image is None):
                id = wiki.split("/")[-1]
                url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{id}"
                resp = requests.get(url, headers=headers)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                wiki_data = resp.json()

                image = wiki_data.get("originalimage", None)
                if doc_image is None and image is not None:
                    image_url = image["source"]
                    filename_with_og_ext = unquote(Path(urlparse(image_url).path).name)
                    filename_with_webp_ext = Path(filename_with_og_ext).stem + ".webp"

                    image_response = requests.get(image_url, headers=headers)
                    image_response.raise_for_status()
                    with tempfile.TemporaryDirectory() as tmpdir:
                        original_path = os.path.join(tmpdir, filename_with_og_ext)
                        webp_path = os.path.join(IMAGE_PATH, filename_with_webp_ext)
                        with open(original_path, "wb") as f:
                            f.write(image_response.content)
                        subprocess.run(
                            [
                                "ffmpeg",
                                "-i",
                                original_path,
                                "-vf",
                                "scale=300:300:force_original_aspect_ratio=decrease",
                                "-q:v",
                                "75",
                                webp_path,
                            ],
                            check=True,
                        )
                        data["image"] = (
                            f"https://download.biblians.com/commentaries/fathers/{filename_with_webp_ext}"
                        )

                summary = wiki_data.get("extract", None)
                if doc_summary is None and summary is not None:
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
        missing = [
            field for field in ("image", "summary", "category") if field not in data
        ]

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


@authors_app.command("image-check")
def find_authors_with_wrong_image():
    target_dir = Path(".")
    for path in target_dir.rglob("metadata.toml"):
        data = Document.parse(path.read_text(encoding="utf-8"))
        image = data.get("image", None)
        if image:
            if not image.startswith("https://download.biblians.com"):
                print(
                    f"{path.parent.name} has an image that does not start with https://download.biblians.com"
                )


# Convert Commands
@convert_app.command("json")
def convert_to_json():
    root_dir = Path(".")
    authors: list[Author] = []
    for path in root_dir.rglob("metadata.toml"):
        author_data = Document.parse(path.read_text(encoding="utf-8"))
        author = Author(
            uuid=str(author_data["uuid"]),
            name=path.parent.name.strip(),
            death_year=int(author_data["default_year"]),
            category=str(author_data["category"]),
            wiki=(str(author_data["wiki"]) if author_data.get("wiki") else None),
            image=(str(author_data["image"]) if author_data.get("image") else None),
            summary=(
                str(author_data["summary"]) if author_data.get("summary") else None
            ),
            commentaries=[],
        )
        for c_path in path.parent.rglob("*.toml"):
            if c_path.name != "metadata.toml":
                commentaries_data = Document.parse(c_path.read_text(encoding="utf-8"))
                ids: set[str] = set()
                for commentary_data in commentaries_data["commentary"]:
                    file_name = c_path.stem
                    fn_pieces = file_name.split(" ")
                    book_name = " ".join(fn_pieces[:-1]).strip()
                    verse_range_str = fn_pieces[-1].strip()
                    verse_range = string_to_verse_range(verse_range_str)
                    location_start = encode_chapter_verse(
                        verse_range.start_chapter, verse_range.start_verse
                    )
                    location_end = encode_chapter_verse(
                        verse_range.end_chapter, verse_range.end_verse
                    )
                    osisId = name_to_osis[book_name]

                    quote = str(commentary_data["quote"].strip())
                    ascii_text = unidecode(quote)
                    normalized_text = re.sub(r"[^a-z0-9]", "", ascii_text.lower())
                    id_key = f"{normalized_text}|{path.parent.name.strip()}|{osisId.lower()}|{verse_range_str}"
                    id = hashlib.sha1(id_key.encode("utf-8")).hexdigest()
                    if id in ids:
                        # Only keep latest one
                        author.commentaries = [
                            c for c in author.commentaries if c.id != id
                        ]

                    ids.add(id)
                    commentary = Commentary(
                        id=id,
                        quote=quote,
                        source_title=(
                            str(commentary_data["source_title"].strip())
                            if commentary_data.get("source_title")
                            else None
                        ),
                        source_url=(
                            str(commentary_data["source_url"])
                            if commentary_data.get("source_url")
                            else None
                        ),
                        append_to_author_name=(
                            str(commentary_data["append_to_author_name"].strip())
                            if commentary_data.get("append_to_author_name")
                            else None
                        ),
                        time=int(
                            commentary_data["time"]
                            if commentary_data.get("time")
                            else author.death_year
                        ),
                        location_start=location_start,
                        location_end=location_end,
                        chapter_start=verse_range.start_chapter,
                        chapter_end=verse_range.end_chapter,
                        osisId=osisId.lower(),
                        display_reference=verse_range_str,
                    )
                    author.commentaries.append(commentary)
        if author.commentaries:
            authors.append(author)
    with open("authors.json", "w", encoding="utf-8") as f:
        json.dump(
            [author.model_dump() for author in authors], f, ensure_ascii=False, indent=4
        )


def main():
    _ = load_dotenv()
    app()


if __name__ == "__main__":
    main()
