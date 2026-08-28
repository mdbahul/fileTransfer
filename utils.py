import os
import shutil
import stat
import tempfile
import time
import zipfile
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


def extract_directory_archive(
    archive_path: str,
    output_directory: str,
    directory_name: str,
) -> str:
    """Safely extract an archive and atomically publish the received directory."""
    validate_filename(directory_name)
    output_path = Path(output_directory) / f"received_{directory_name}"
    if output_path.exists():
        raise ValueError("Destination directory already exists")

    temporary_path = Path(
        tempfile.mkdtemp(
            prefix=f".received_{directory_name}.",
            dir=output_directory,
        )
    ).resolve()
    seen_names: set[str] = set()

    try:
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                name = info.filename
                if (
                    not name
                    or "\x00" in name
                    or "\\" in name
                    or Path(name).is_absolute()
                    or PureWindowsPath(name).is_absolute()
                    or PureWindowsPath(name).drive
                ):
                    raise ValueError("Archive contains an unsafe path")

                relative_path = Path(name)
                if ".." in relative_path.parts or name in seen_names:
                    raise ValueError("Archive contains an unsafe path")
                seen_names.add(name)

                mode = (info.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    raise ValueError("Archive contains a symlink")
                if mode not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ValueError("Archive contains an unsupported entry")

                destination = temporary_path / relative_path
                resolved_destination = destination.resolve()
                if (
                    resolved_destination != temporary_path
                    and temporary_path not in resolved_destination.parents
                ):
                    raise ValueError("Archive contains an unsafe path")

                if info.is_dir() or name.endswith("/"):
                    destination.mkdir(parents=True, exist_ok=True)
                    continue

                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists() and not destination.is_file():
                    raise ValueError("Archive contains conflicting entries")
                with archive.open(info) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)

        os.replace(temporary_path, output_path)
        sync_directory(output_directory)
        return str(output_path)
    except zipfile.BadZipFile as error:
        shutil.rmtree(temporary_path, ignore_errors=True)
        raise ValueError("Invalid directory archive") from error
    except (OSError, ValueError, zipfile.BadZipFile):
        shutil.rmtree(temporary_path, ignore_errors=True)
        raise
