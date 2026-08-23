import hashlib
import os

def calculate_sha256(file_path, block_size=65536):
    """
    Calculate the SHA-256 checksum of a file by streaming it in chunks.
    This prevents high memory usage for large files.
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(block_size), b""):
            sha256.update(block)
    return sha256.hexdigest()

def sanitize_filename(filename):
    """
    Sanitize the filename to prevent path traversal attacks.
    E.g., '../../etc/passwd' or '..\\..\\..\\boot.ini' becomes 'boot.ini'/'passwd'.
    This is fully cross-platform (handling Windows separators on macOS/Linux and vice-versa).
    """
    # 1. Convert all Windows backslashes to forward slashes to ensure uniform processing
    normalized = filename.replace("\\", "/")
    
    # 2. Extract the base filename using os.path.basename
    base = os.path.basename(normalized)
    
    # 3. Strip any residual slashes just to be absolutely certain
    base = base.replace("/", "")
    
    # 4. If the filename is empty or evaluates to relative dots, assign a safe fallback
    if not base or base in (".", ".."):
        base = "unnamed_transfer"
        
    return base
