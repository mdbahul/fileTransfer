import os
import time
from pathlib import Path, PureWindowsPath


def format_bytes(value: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(value)
    unit_index = 0

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    return f"{size:.1f} {units[unit_index]}"


def validate_filename(filename: str) -> str:
    """
    Validate a filename received from a peer.

    Returns the filename if it is safe.
    Raises ValueError if it contains path traversal or directory components.
    """
    path = Path(filename)
    windows_path = PureWindowsPath(filename)

    if (
        not filename
        or "\x00" in filename
        or path.is_absolute()
        or windows_path.is_absolute()
        or ".." in path.parts
        or ".." in windows_path.parts
        or len(path.parts) != 1
        or len(windows_path.parts) != 1
    ):
        raise ValueError("Invalid filename")

    return filename


def cleanup_expired_transfers(
    output_directory: str,
    retention_seconds: int,
) -> None:
    if retention_seconds < 0:
        raise ValueError("Retention period cannot be negative")

    now = time.time()
    for meta_path in Path(output_directory).glob("*.meta"):
        try:
            age = now - meta_path.stat().st_mtime
            if age <= retention_seconds:
                continue

            part_path = meta_path.with_suffix(".part")
            if part_path.exists():
                part_path.unlink()
            meta_path.unlink()
        except OSError as error:
            print(f"Resume cleanup failed for {meta_path.name}: {error}")


def sync_directory(directory: str) -> None:
    if os.name != "posix":
        return

    directory_fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)