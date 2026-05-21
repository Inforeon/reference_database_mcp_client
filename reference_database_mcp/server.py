from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from reference_database_mcp.config import parse_args

# MCP instance (must be defined before decorators)
mcp = FastMCP("reference_database")

_server_url: str = "http://localhost:8000"
_client: httpx.AsyncClient | None = None


def init(server_url: str) -> None:
    global _server_url
    _server_url = server_url


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=_server_url, timeout=120)
    return _client


async def _close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ── Health ───────────────────────────────────────────────────────────


@mcp.tool(name="health_check", description="Check if the reference database server is running and healthy.")
async def health_check() -> dict[str, Any]:
    """Return server status information including database path."""
    client = _get_client()
    resp = await client.get("/api/health")
    resp.raise_for_status()
    return resp.json()


# ── Index Management ────────────────────────────────────────────────
# Mostly not tools the agent should be using

# Recursively scans a directory for existing files
#@mcp.tool(name="scan_index", description="Scan a directory tree and sync the index on the server.")
async def scan_index(
    dirpath: str,
    recursive: bool = True,
    document_type: str = "generic",
    extra_metadata: str = "{}",
) -> dict[str, Any]:
    """Scan a directory and add/update/remove entries in the index.

    Args:
        dirpath: Directory path to scan (relative to database home).
        recursive: Whether to scan subdirectories recursively.
        document_type: Type of documents to index (e.g. 'generic', 'paper').
        extra_metadata: JSON-encoded dict of extra metadata to apply.
    """
    client = _get_client()
    try:
        meta = json.loads(extra_metadata)
    except json.JSONDecodeError:
        meta = {}
    resp = await client.post(
        "/api/index/scan",
        json={
            "dirpath": dirpath,
            "recursive": recursive,
            "document_type": document_type,
            "extra_metadata": meta,
        },
    )
    resp.raise_for_status()
    return resp.json()

# Add existing file already on the server to index
# @mcp.tool(name="add_to_index", description="Add a single file to the index by its filesystem path.")
async def add_to_index(
    filepath: str,
    document_type: str = "generic",
    extra_metadata: str = "{}",
) -> dict[str, Any]:
    """Add a single file to the index.

    Args:
        filepath: Path to the file (relative to database home).
        document_type: Type of document (e.g. 'generic', 'paper').
        extra_metadata: JSON-encoded dict of extra metadata.
    """
    client = _get_client()
    try:
        meta = json.loads(extra_metadata)
    except json.JSONDecodeError:
        meta = {}
    resp = await client.post(
        "/api/index/add",
        json={
            "filepath": filepath,
            "document_type": document_type,
            "extra_metadata": meta,
        },
    )
    resp.raise_for_status()
    return resp.json()


#
@mcp.tool(name="remove_from_index", description="Remove a file from the index by its path.")
async def remove_from_index(filepath: str) -> dict[str, Any]:
    """Remove a file from the index.

    Args:
        filepath: Path to the file to remove (relative to database home).
    """
    client = _get_client()
    resp = await client.post(
        "/api/index/remove",
        json={"filepath": filepath},
    )
    resp.raise_for_status()
    return resp.json()

# List contents of a directory. This one's fine
@mcp.tool(name="list_folder", description="List files and subdirectories of an indexed directory in the reference database.")
async def browse_filesystem(path: str = "") -> dict[str, Any]:
    """Browse the indexed filesystem of the database home.

    Args:
        path: Relative directory path within the database home (default: root).
    """
    client = _get_client()
    resp = await client.get("/api/fs", params={"path": path})
    resp.raise_for_status()
    return resp.json()


# ── Search ───────────────────────────────────────────────────────────


@mcp.tool(name="search_documents", description="""Search indexed documents and textbook chapters by full-text query.
    Returns a structured response with two groups:
      - ``documents``: generic/paper document-level hits (and textbook title-level hits).
      - ``chapters``: textbook chapter-level hits with parent textbook context.

    Args:
        query: Full-text search query string. Searches titles and text content
        scope: Restrict results to a subdirectory prefix.
        file_type: Filter by file extension (e.g. "pdf").
        author: Filter by author field in metadata (somewhat unreliable).
        tags: Comma-separated list of tags to filter by.
        after: Only include documents modified after this ISO date.
        before: Only include documents modified before this ISO date.
        document_types: Comma-separated types to include from {paper,textbook,generic}. Empty means all.
        offset: Pagination offset (default 0).
        limit: Maximum number of results per group (default 50).
    
    Returned indexed IDs plus additional information
""")
async def search_documents(
    query: str = "",
    scope: str = "",
    file_type: str = "",
    author: str = "",
    tags: str = "",
    after: str = "",
    before: str = "",
    document_types: str = "",
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    """Search indexed documents and textbook chapters by full-text query.

    Returns a structured response with two groups:
      - ``documents``: generic/paper document-level hits (and textbook title-level hits).
      - ``chapters``: textbook chapter-level hits with parent textbook context.

    Args:
        query: Full-text search query string.
        scope: Restrict results to a subdirectory prefix.
        file_type: Filter by file extension (e.g. "pdf").
        author: Filter by author field in metadata.
        tags: Comma-separated list of tags to filter by.
        after: Only include documents modified after this ISO date.
        before: Only include documents modified before this ISO date.
        document_types: Comma-separated types to include (e.g. "paper,textbook"). Empty means all.
        offset: Pagination offset (default 0).
        limit: Maximum number of results per group (1-200, default 50).
    """
    client = _get_client()
    resp = await client.get(
        "/api/search",
        params={
            "q": query,
            "scope": scope,
            "file_type": file_type,
            "author": author,
            "tags": tags,
            "after": after,
            "before": before,
            "document_types": document_types,
            "offset": offset,
            "limit": limit,
        },
    )
    resp.raise_for_status()
    return resp.json()


# ── Documents ────────────────────────────────────────────────────────


@mcp.tool(name="get_document", description="Retrieve metadata for an indexed document by indexed ID.")
async def get_document(doc_id: int) -> dict[str, Any]:
    """Retrieve metadata for an indexed document by its internal ID.

    Args:
        doc_id: The internal document ID of the document.
    """
    client = _get_client()
    resp = await client.get(f"/api/documents/{doc_id}")
    resp.raise_for_status()
    return resp.json()


@mcp.tool(name="get_document_content", description="Retrieve the extracted text content of a document by indexed ID.")
async def get_document_content(doc_id: int) -> dict[str, Any]:
    """Retrieve the extracted text content of a document.

    Args:
        doc_id: Internal document ID of the document.
    """
    client = _get_client()
    resp = await client.get(f"/api/documents/{doc_id}/content")
    resp.raise_for_status()
    return resp.json()


@mcp.tool(name="download_document_file", description="Download the original file for a document to a local path by indexed ID.")
async def download_document_file(doc_id: int, save_path: str) -> dict[str, Any]:
    """Download the original file for a document to a local path.

    Args:
        doc_id: Internal document ID.
        save_path: Local filesystem path where the file should be saved.
    """
    client = _get_client()
    resp = await client.get(f"/api/documents/{doc_id}/file")
    resp.raise_for_status()

    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(resp.content)

    return {"saved_to": save_path, "size": len(resp.content)}


@mcp.tool(name="get_document_meta", description="Retrieve the sidecar metadata for a document by indexed ID.")
async def get_document_meta(doc_id: int) -> dict[str, Any]:
    """Retrieve the sidecar metadata for a document.

    Args:
        doc_id: Internal document ID.
    """
    client = _get_client()
    resp = await client.get(f"/api/documents/{doc_id}/meta")
    resp.raise_for_status()
    return resp.json()


@mcp.tool(name="update_document_meta", description="Update a single key/value pair in a document's sidecar metadata by indexed ID.")
async def update_document_meta(doc_id: int, key: str, value: Any) -> dict[str, Any]:
    """Update a single key/value pair in a document's sidecar metadata.

    Args:
        doc_id: Internal document ID.
        key: The metadata key to set.
        value: The value to assign (any JSON-serializable type).
    """
    client = _get_client()
    resp = await client.patch(
        f"/api/documents/{doc_id}/meta",
        json={"key": key, "value": value},
    )
    resp.raise_for_status()
    return resp.json()


@mcp.tool(name="get_document_bibtex", description="Export BibTeX citation data for a document by indexed ID. Only applicable to documents of type 'paper'")
async def get_document_bibtex(doc_id: int) -> dict[str, Any]:
    """Export BibTeX citation data for a research paper.

    Args:
        doc_id: Internal document ID (must be a paper-type document).
    """
    client = _get_client()
    resp = await client.get(f"/api/documents/{doc_id}/bibtex")
    resp.raise_for_status()
    return resp.json()


@mcp.tool(name="move_document", description="Move a document to a different location within the database by indexed ID.")
async def move_document(doc_id: int, destination: str) -> dict[str, Any]:
    """Move a document to a new location within the database home.

    The destination is resolved relative to the database home when relative.
    Parent directories are created automatically.

    Args:
        doc_id: Internal document ID of the document to move.
        destination: The new path for the document (relative to database home or absolute).
    """
    client = _get_client()
    resp = await client.post(
        f"/api/documents/{doc_id}/move",
        json={"destination": destination},
    )
    resp.raise_for_status()
    return resp.json()


@mcp.tool(name="attach_file", description="Attach a physical file to an existing reference-only document entry by indexed ID.")
async def attach_file(
    doc_id: int,
    filepath: str,
    directory: str = "",
    filename: str = "",
) -> dict[str, Any]:
    """Attach a physical file to a reference-only entry, converting it to source_type='file'.

    The existing metadata from the reference entry is preserved and merged with any
    metadata extracted from the uploaded file.

    Args:
        doc_id: Internal document ID of the reference entry.
        filepath: Local path to the file to attach.
        directory: Server-side subdirectory within the database home (default: root).
        filename: Override the filename on the server (default: use original name).
    """
    client = _get_client()
    with open(filepath, "rb") as f:
        resp = await client.post(
            f"/api/documents/{doc_id}/attach",
            params={
                "directory": directory,
                "filename": filename or "",
            },
            files={"file": (Path(filepath).name, f, "application/octet-stream")},
        )
    resp.raise_for_status()
    return resp.json()


@mcp.tool(name="detach_file", description="Detach the physical file from a document, converting it to a reference-only entry by indexed ID.")
async def detach_file(doc_id: int) -> dict[str, Any]:
    """Detach the physical file from a document, converting it to source_type='reference'.

    Deletes the main file from disk but preserves the sidecar metadata (.meta.json).
    Clears full_text and extracted_metadata since there is no longer a file to extract from.

    Args:
        doc_id: Internal document ID of the document to detach.
    """
    client = _get_client()
    resp = await client.post(f"/api/documents/{doc_id}/detach")
    resp.raise_for_status()
    return resp.json()


# ── Upload ───────────────────────────────────────────────────────────


@mcp.tool(name="upload_file", description="""
Read a file from the local filesystem and upload it to the server for indexing.
Args:
    filepath: Local path to the file to upload.
    directory: Server-side subdirectory within the database home (default: database root).
    filename: Optional, new name to save file as on server.
    extra_metadata: Optional. JSON-encoded dict of extra metadata. Can add to or overwrite existing metadata on file.
""")
async def upload_file(
    filepath: str,
    directory: str = "",
    filename: str = "",
    extra_metadata: str = "{}",
) -> dict[str, Any]:
    """Read a file from the local filesystem and upload it to the server for indexing.

    Args:
        filepath: Local path to the file to upload.
        directory: Server-side subdirectory within the database home (default: root).
        filename: Override the filename on the server (default: use original name).
        extra_metadata: JSON-encoded dict of extra metadata.
    """
    client = _get_client()
    with open(filepath, "rb") as f:
        resp = await client.post(
            "/api/documents/upload",
            params={
                "directory": directory,
                "filename": filename or "",
                "extra_metadata": extra_metadata or "",
            },
            files={"file": (Path(filepath).name, f, "application/octet-stream")},
        )
    resp.raise_for_status()
    return resp.json()

# Agent shouldn't use this one. It's for papers with a file already existing on the server
# @mcp.tool(name="add_paper", description="Add a research paper to the index by filesystem path on the server.")
async def add_paper(
    filepath: str,
    doi: str = "",
    skip_bib: bool = False,
    extra_metadata: str = "{}",
) -> dict[str, Any]:
    """Add a research paper to the index by its filesystem path on the server.

    Supports optional DOI embedding before bibliographic extraction via pdf2bib.

    Args:
        filepath: Path to the paper file on the server (relative to database home).
        doi: Known DOI to embed before bibliographic extraction.
        skip_bib: If True, skip pdf2bib entirely.
        extra_metadata: JSON-encoded dict of extra metadata.
    """
    client = _get_client()
    try:
        meta = json.loads(extra_metadata)
    except json.JSONDecodeError:
        meta = {}
    resp = await client.post(
        "/api/documents/papers/add",
        json={
            "filepath": filepath,
            "doi": doi or None,
            "skip_bib": skip_bib,
            "extra_metadata": meta,
        },
    )
    resp.raise_for_status()
    return resp.json()


@mcp.tool(name="upload_paper", description="""
Upload a research paper PDF to the server for indexing.
Note: papers have their metadata extracted and searched by pdf2bib for use in reference generation. This process is
inaccurate and often results in the wrong DOI being extracted. To guard against this, it is checked that the title of
the paper under the retrieved DOI matches the uploaded paper's title, and an error is thrown if it doesn't. It is
recommended that a DOI be provided manually here to skip the extraction step. If an error still occurs, the skip_bib
flag can be used to skip the reference generation step entirely
 
Args:
    filepath: Local path to the PDF file to upload.
    directory: Server-side subdirectory to save the file to.
    filename: Optional, new filename for the paper on the server.
    doi: Optional. Known DOI to embed before pdf2bib bibliographic extraction.
    skip_bib: Optional. skip pdf2bib reference generation.
    extra_metadata: Optional. JSON-encoded dict of metadata to add to or overwrite on the file.
""")
async def upload_paper(
    filepath: str,
    directory: str = "",
    filename: str = "",
    doi: str = "",
    skip_bib: bool = False,
    extra_metadata: str = "{}",
) -> dict[str, Any]:
    """Read a paper PDF from the local filesystem and upload it to the server.

    Args:
        filepath: Local path to the PDF file to upload.
        directory: Server-side subdirectory within the database home.
        filename: Override the filename on the server.
        doi: Known DOI to embed before bibliographic extraction.
        skip_bib: If True, skip pdf2bib entirely.
        extra_metadata: JSON-encoded dict of extra metadata.
    """
    client = _get_client()
    with open(filepath, "rb") as f:
        resp = await client.post(
            "/api/documents/papers/upload",
            params={
                "directory": directory,
                "filename": filename or "",
                "doi": doi or "",
                "skip_bib": skip_bib,
                "extra_metadata": extra_metadata or "",
            },
            files={"file": (Path(filepath).name, f, "application/pdf")},
        )
    resp.raise_for_status()
    return resp.json()


@mcp.tool(name="upload_textbook", description="""
Upload a textbook to the server for indexing. The server accepts two types of textbooks, specified under the 'variant'
argument here: 'file' or 'directory'. A file is a textbook in a single pdf file, with chapters denoted by page indices.
a directory is a textbook represented by a folder where each file is a chapter. To upload a file type textbook, use
this endpoint with filepath !=None. Optionally, chapter_breakpoints can specify chapter page ranges, or if not, chapters
will be automatically extracted from the documents ToC. To upload a directory type textbook, use this endpoint with
filepath=None to declare the textbook directory, followed by a number of calls to upload_chapter,
using the textbook ID returned here to upload each chapter of the textbook. 

Args:
    filepath: Local path to the PDF file to upload (for variant="file"), or None (for variant='directory').
    directory: Server-side subdirectory within the database home to upload the textbook to.
    filename Name of the textbook's file/directory name on the server (required for variant='directory').
    variant: "file" to upload a single-PDF textbook, "directory" to create an empty textbook directory.
    chapter_breakpoints: Optional. For variant='file' only. Accepts either a list of integers, representing
        the breakpoints between chapters with auto-generated chapter names, or a dict with chapter names as keys,
        and the end page of the chapter as values to determine the breakpoints. The first chapter is assumed to start at page 0.
        The last chapter should be specified with end page None.
    extra_metadata: Optional. JSON-encoded dict of extra metadata (can still be used with directory textbooks).
""")
async def upload_textbook(
    filepath: str | None = None,
    directory: str = "",
    filename: str = "",
    variant: str = "file",
    extra_metadata: str = "{}",
) -> dict[str, Any]:
    """Upload a textbook PDF or create an empty directory-type textbook on the server.

    Args:
        filepath: Local path to the PDF file to upload (required when variant="file").
        directory: Server-side subdirectory within the database home.
        filename: Override the filename on the server.
        variant: "file" to upload a single-PDF textbook, "directory" to create an empty textbook container.
        extra_metadata: JSON-encoded dict of extra metadata.
    """
    client = _get_client()
    if variant == "directory":
        resp = await client.post(
            "/api/documents/textbooks/upload",
            params={
                "directory": directory,
                "filename": filename or "",
                "variant": "directory",
                "extra_metadata": extra_metadata or "",
            },
        )
    else:
        if filepath is None:
            raise ValueError("file_path is required when variant='file'")
        with open(filepath, "rb") as f:
            resp = await client.post(
                "/api/documents/textbooks/upload",
                params={
                    "directory": directory,
                    "filename": filename or "",
                    "variant": "file",
                    "extra_metadata": extra_metadata or "",
                },
                files={"file": (Path(filepath).name, f, "application/pdf")},
            )
    resp.raise_for_status()
    return resp.json()


# ── Chapters ─────────────────────────────────────────────────────────


@mcp.tool(name="upload_chapter", description="Upload a chapter file to a directory-type textbook by ID. Chapter_index auto-increments if not specified, and overwrites an existing chapter if it already exists")
async def upload_chapter(
    doc_id: int,
    file_path: str,
    filename: str = "",
    chapter_index: int | None = None,
) -> dict[str, Any]:
    """Upload a chapter file to a directory-type textbook.

    The file is saved into the textbook's directory on the server and indexed as a
    new chapter. If ``chapter_index`` is omitted it is auto-assigned. Only works
    for textbooks created with ``variant="directory"``.

    Args:
        doc_id: Internal document ID of the parent textbook.
        file_path: Local path to the chapter file to upload.
        filename: Override the filename on the server (default: use original name).
        chapter_index: Explicit zero-based index (auto-assigned if omitted).
    """
    client = _get_client()
    params: dict[str, Any] = {
        "filename": filename or "",
    }
    if chapter_index is not None:
        params["chapter_index"] = chapter_index

    with open(file_path, "rb") as f:
        resp = await client.post(
            f"/api/documents/textbooks/{doc_id}/chapters/upload",
            params=params,
            files={"file": (Path(file_path).name, f, "application/octet-stream")},
        )
    resp.raise_for_status()
    return resp.json()


# ── References (metadata-only, no file) ─────────────────────────────


@mcp.tool(name="add_paper_reference", description="Register a paper reference entry without uploading a file, for citation purposes.")
async def add_paper_reference(
    title: str,
    filepath: str = "",
    author: str = "",
    year: str = "",
    journal: str = "",
    booktitle: str = "",
    doi: str = "",
    url: str = "",
    bibtex: str = "",
    citation_key: str = "",
    extra_metadata: str = "{}",
) -> dict[str, Any]:
    """Register a paper reference entry without uploading any file.

    Creates a metadata-only document with ``source_type='reference'``. BibTeX is
    auto-generated if not provided.

    Args:
        title: Title of the paper.
        filepath: Path within the database home for grouping (file need not exist yet).
        author: Author(s).
        year: Publication year.
        journal: Journal name.
        booktitle: Conference or book title.
        doi: Digital Object Identifier.
        url: URL to the paper.
        bibtex: Raw BibTeX entry string.
        citation_key: Citation key for BibTeX.
        extra_metadata: JSON-encoded dict of additional metadata.
    """
    client = _get_client()
    body: dict[str, Any] = {"title": title}
    if filepath:
        body["filepath"] = filepath
    if author:
        body["author"] = author
    if year:
        body["year"] = year
    if journal:
        body["journal"] = journal
    if booktitle:
        body["booktitle"] = booktitle
    if doi:
        body["doi"] = doi
    if url:
        body["url"] = url
    if bibtex:
        body["bibtex"] = bibtex
    if citation_key:
        body["citation_key"] = citation_key
    try:
        body["extra_metadata"] = json.loads(extra_metadata)
    except json.JSONDecodeError:
        body["extra_metadata"] = {}

    resp = await client.post("/api/documents/papers/reference", json=body)
    resp.raise_for_status()
    return resp.json()


@mcp.tool(name="add_textbook_reference", description="Register a textbook reference entry without uploading any file for citation purposes.")
async def add_textbook_reference(
    title: str,
    filepath: str = "",
    author: str = "",
    year: str = "",
    publisher: str = "",
    edition: str = "",
    url: str = "",
    extra_metadata: str = "{}",
) -> dict[str, Any]:
    """Register a textbook reference entry without uploading any file.

    Creates a metadata-only document with ``source_type='reference'`` and
    ``document_type='textbook'``.

    Args:
        title: Title of the textbook.
        filepath: Path within the database home for grouping (file need not exist yet).
        author: Author(s).
        year: Publication year.
        publisher: Publisher name.
        edition: Edition string.
        url: URL to the textbook.
        extra_metadata: JSON-encoded dict of additional metadata.
    """
    client = _get_client()
    body: dict[str, Any] = {"title": title}
    if filepath:
        body["filepath"] = filepath
    if author:
        body["author"] = author
    if year:
        body["year"] = year
    if publisher:
        body["publisher"] = publisher
    if edition:
        body["edition"] = edition
    if url:
        body["url"] = url
    try:
        body["extra_metadata"] = json.loads(extra_metadata)
    except json.JSONDecodeError:
        body["extra_metadata"] = {}

    resp = await client.post("/api/documents/textbooks/reference", json=body)
    resp.raise_for_status()
    return resp.json()


@mcp.tool(name="add_generic_reference", description="Register a generic document reference without uploading any file for citation purposes.")
async def add_generic_reference(
    title: str,
    filepath: str = "",
    author: str = "",
    subject: str = "",
    keywords: str = "",
    url: str = "",
    extra_metadata: str = "{}",
) -> dict[str, Any]:
    """Register a generic document reference without uploading any file.

    Creates a metadata-only document with ``source_type='reference'`` and
    ``document_type='generic'``.

    Args:
        title: Title of the document.
        filepath: Path within the database home for grouping (file need not exist yet).
        author: Author(s).
        subject: Subject or description.
        keywords: Comma-separated list of keywords.
        url: URL to the document.
        extra_metadata: JSON-encoded dict of additional metadata.
    """
    client = _get_client()
    body: dict[str, Any] = {"title": title}
    if filepath:
        body["filepath"] = filepath
    if author:
        body["author"] = author
    if subject:
        body["subject"] = subject
    if keywords:
        body["keywords"] = [k.strip() for k in keywords.split(",") if k.strip()]
    if url:
        body["url"] = url
    try:
        body["extra_metadata"] = json.loads(extra_metadata)
    except json.JSONDecodeError:
        body["extra_metadata"] = {}

    resp = await client.post("/api/documents/reference", json=body)
    resp.raise_for_status()
    return resp.json()


# ── Textbooks ────────────────────────────────────────────────────────


@mcp.tool(name="list_chapters", description="List all chapters for a textbook document by ID.")
async def list_chapters(doc_id: int) -> list[dict[str, Any]]:
    """List all chapters for a textbook document.

    Args:
        doc_id: Internal document ID of the textbook.
    """
    client = _get_client()
    resp = await client.get(f"/api/documents/textbooks/{doc_id}/chapters")
    resp.raise_for_status()
    return resp.json()


@mcp.tool(name="get_chapter", description="Retrieve a specific chapter from a textbook including full text.")
async def get_chapter(doc_id: int, chapter_index: int) -> dict[str, Any]:
    """Retrieve a specific chapter from a textbook, including full text.

    Args:
        doc_id: Internal document ID of the parent textbook.
        chapter_index: Zero-based index of the chapter to retrieve.
    """
    client = _get_client()
    resp = await client.get(f"/api/documents/textbooks/{doc_id}/chapters/{chapter_index}")
    resp.raise_for_status()
    return resp.json()


# ── Entrypoint ───────────────────────────────────────────────────────

#@mcp.tool(name="get_settings", description="get the current configuration of the mcp server. This is a debugging tool")
async def get_settings() -> Any:
    global _server_url
    return _server_url

def main() -> None:
    """Start the MCP server."""
    args = parse_args()
    init(args.server_url)
    mcp.run()
    #asyncio.run(health_check())

if __name__ == "__main__":
    main()
