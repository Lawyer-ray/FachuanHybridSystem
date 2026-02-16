"""Module for folder node path."""

from __future__ import annotations


def normalize_folder_node_path(folder_node_path: str) -> str:
    if not folder_node_path:
        return ""

    path_parts = folder_node_path.split("/")
    if len(path_parts) <= 1:
        return folder_node_path

    if not path_parts[0].startswith(("1-", "2-", "3-", "4-", "5-", "6-", "7-", "8-", "9-")):
        return "/".join(path_parts[1:])

    return folder_node_path
