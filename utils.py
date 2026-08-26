from pathlib import Path, PureWindowsPath


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