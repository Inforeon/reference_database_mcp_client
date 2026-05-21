# reference-database-mcp

MCP (Model Context Protocol) server wrapper for the **reference database** (docsearch) REST API.

Provides tools that allow an LLM to search, retrieve, upload, and manage documents stored in a reference database server.

## Tools

### Health & Indexing

| Tool | Description |
|---|---|
| `health_check` | Check if the server is running and healthy |
| `remove_from_index` | Remove a file from the index by path |
| `list_folder` | List files and subdirectories of an indexed directory |

### Search

| Tool | Description |
|---|---|
| `search_documents` | Full-text search across documents and textbook chapters |

### Documents

| Tool | Description |
|---|---|
| `get_document` | Get metadata for an indexed document by ID |
| `get_document_content` | Get the extracted text content of a document |
| `download_document_file` | Download the original file to a local path |
| `get_document_meta` | Get sidecar metadata for a document |
| `update_document_meta` | Update a key/value pair in sidecar metadata |
| `get_document_bibtex` | Export BibTeX citation data for a paper |
| `move_document` | Move a document to a new location within the database |

### Upload

| Tool | Description |
|---|---|
| `upload_file` | Upload a local file to the server for indexing |
| `upload_paper` | Upload a paper PDF with optional DOI embedding |
| `upload_textbook` | Upload a textbook PDF or create a directory-type textbook |
| `upload_chapter` | Upload a chapter file to a directory-type textbook |

### References (metadata-only)

| Tool | Description |
|---|---|
| `add_paper_reference` | Register a paper reference without uploading a file |
| `add_textbook_reference` | Register a textbook reference without uploading a file |
| `add_generic_reference` | Register a generic document reference without uploading a file |

### Textbooks

| Tool | Description |
|---|---|
| `list_chapters` | List all chapters in a textbook |
| `get_chapter` | Retrieve a specific chapter with full text |

## Setup

```bash
pip install -e .
```

## Usage

```bash
reference-database-mcp --server-url http://localhost:8000
```

Or via your MCP client's stdio/SSE transport configuration.

## Disabled Tools

The following tools exist in code but are disabled (their `@mcp.tool` decorator is commented out). They can be re-enabled by uncommenting their decorators:

| Tool | Endpoint | Reason |
|---|---|---|
| `scan_index` | `POST /api/index/scan` | Recursively scans directories; not intended for agent use |
| `add_to_index` | `POST /api/index/add` | Adds existing server-side files to index; not intended for agent use |
| `add_paper` | `POST /api/documents/papers/add` | Adds papers by server-side path; prefer `upload_paper` instead |
