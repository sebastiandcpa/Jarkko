"""Modelos de ``/api/files/*``."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FileEntry(BaseModel):
    name: str
    path: str
    type: str = Field(description="file | directory")
    size: int | None = None
    modified: str | None = None


class FileSearchResponse(BaseModel):
    query: str
    root_path: str
    total: int
    truncated: bool = False
    scanned: int = 0
    results: list[FileEntry] = Field(default_factory=list)


class FileListResponse(BaseModel):
    path: str
    total: int
    directories: int = 0
    files: int = 0
    truncated: bool = False
    entries: list[FileEntry] = Field(default_factory=list)


class KnownFoldersResponse(BaseModel):
    folders: dict[str, str] = Field(default_factory=dict)
