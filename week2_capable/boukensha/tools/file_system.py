import os
import re
from pathlib import Path


def register(registry, *, working_dir):
    """Register the standard file-oriented tools, sandboxed to one root.

    Tools registered:
      pwd              — return the working directory
      list_directory   — list files and subdirectories at a path
      read_file        — read the full contents of a file
      write_file       — write (or overwrite) a file
      delete_file      — delete a file
      search_files     — grep for a pattern across files in the working tree

    Every path the agent supplies is resolved relative to that root. A path that
    would escape the root returns an *error string* rather than raising, so the
    agent sees it and can try something sensible instead.
    """
    root = os.path.abspath(os.path.expanduser(working_dir))

    def resolve(path):
        """Resolve an agent-supplied path inside root. Returns the absolute path,
        or an error string.

        Deliberately `os.path.abspath(os.path.join(...))` rather than
        `Path.resolve()`. Ruby's File.expand_path is purely lexical — it
        normalises `..` without touching the filesystem — while `Path.resolve()`
        also follows symlinks and behaves differently for paths that do not
        exist. Matching Ruby's semantics keeps the containment rule identical
        across the two languages, which is what the cross-language gate checks.
        """
        absolute = os.path.abspath(os.path.join(root, str(path)))
        if absolute == root or absolute.startswith(root + os.sep):
            return absolute
        return f"error: path '{path}' escapes the working directory"

    def oops(msg):
        return f"error: {msg}"

    @registry.tool(
        "pwd",
        description="Return the working directory — the root that all file paths are relative to.",
        parameters={},
    )
    def pwd():
        return root

    @registry.tool(
        "list_directory",
        description=(
            "List files and subdirectories at a path relative to the working directory. "
            "Defaults to the working directory itself."
        ),
        parameters={
            "path": {"type": "string", "description": "Relative path to list (default '.')"}
        },
    )
    def list_directory(path="."):
        target = resolve(path)
        if target.startswith("error:"):
            return target
        if not os.path.isdir(target):
            return oops(f"'{path}' is not a directory")

        entries = sorted(os.listdir(target))
        rendered = [
            f"{name}/" if os.path.isdir(os.path.join(target, name)) else name
            for name in entries
        ]
        return "\n".join(rendered) if rendered else "(empty)"

    @registry.tool(
        "read_file",
        description=(
            "Read and return the full contents of a file. Path is relative to the "
            "working directory."
        ),
        parameters={
            "path": {"type": "string", "description": "Relative path to the file"}
        },
    )
    def read_file(path):
        target = resolve(path)
        if target.startswith("error:"):
            return target
        if not os.path.isfile(target):
            return oops(f"'{path}' is not a file")

        try:
            return Path(target).read_text()
        except OSError as e:
            return oops(str(e))

    @registry.tool(
        "write_file",
        description=(
            "Write content to a file, creating it (and any missing parent directories) "
            "if needed, overwriting if it exists. Path is relative to the working directory."
        ),
        parameters={
            "path": {"type": "string", "description": "Relative path to the file"},
            "content": {"type": "string", "description": "Text content to write"},
        },
    )
    def write_file(path, content):
        target = resolve(path)
        if target.startswith("error:"):
            return target

        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            Path(target).write_text(content)
        except OSError as e:
            return oops(str(e))

        rel = target[len(root) + 1:] if target.startswith(root + os.sep) else target
        # bytesize, not length — Ruby reports bytes and the agent may write UTF-8.
        return f"ok: wrote {len(content.encode('utf-8'))} bytes to {rel}"

    @registry.tool(
        "delete_file",
        description=(
            "Delete a file. Directories are not deleted. Path is relative to the "
            "working directory."
        ),
        parameters={
            "path": {"type": "string", "description": "Relative path to the file to delete"}
        },
    )
    def delete_file(path):
        target = resolve(path)
        if target.startswith("error:"):
            return target
        if not os.path.isfile(target):
            return oops(f"'{path}' is not a file")

        try:
            os.remove(target)
        except OSError as e:
            return oops(str(e))
        return f"ok: deleted {path}"

    @registry.tool(
        "search_files",
        description=(
            "Search for a text pattern (literal string or regex) across all files in the "
            "working directory tree. Returns matching lines in 'path:line_number:content' format."
        ),
        parameters={
            "pattern": {"type": "string", "description": "The text or regex pattern to search for"},
            "path": {
                "type": "string",
                "description": "Subdirectory or file to search within (default '.' = entire working directory)",
            },
            "glob": {
                "type": "string",
                "description": "File glob to restrict which files are searched, e.g. '*.py' (default '*')",
            },
        },
    )
    def search_files(pattern, path=".", glob="*"):
        target = resolve(path)
        if target.startswith("error:"):
            return target

        try:
            regex = re.compile(pattern)
        except re.error as e:
            return oops(f"invalid pattern: {e}")

        if os.path.isfile(target):
            candidates = [target]
        else:
            candidates = sorted(str(p) for p in Path(target).rglob(glob))

        matches = []
        for file in candidates:
            if not os.path.isfile(file):
                continue
            rel = file[len(root) + 1:] if file.startswith(root + os.sep) else file
            try:
                with open(file, "r", errors="replace") as fh:
                    for lineno, line in enumerate(fh, start=1):
                        if regex.search(line):
                            matches.append(f"{rel}:{lineno}:{line.rstrip(chr(10))}")
            except OSError as e:
                matches.append(f"{rel}: error reading file: {e}")

        return "\n".join(matches) if matches else "no matches"
