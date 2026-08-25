def format_bytes(value: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(value)
    unit_index = 0

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    return f"{size:.1f} {units[unit_index]}"


def render_progress(
    filename: str,
    transferred: int,
    total: int,
    elapsed: float,
    first_render: bool,
) -> None:
    
    if not first_render:
        print("\033[5F", end="")

    percentage = (transferred / total) * 100 if total else 100
    bar_width = 20
    filled = min(bar_width, int((percentage / 100) * bar_width))
    progress_bar = "█" * filled + "░" * (bar_width - filled)

    if elapsed > 0 and transferred > 0:
        speed = transferred / elapsed
        eta = (total - transferred) / speed
        speed_text = f"{format_bytes(int(speed))}/s"
        eta_text = f"{eta:.0f} sec"
    else:
        speed_text = "unavailable"
        eta_text = "unavailable"

    lines = (
        filename,
        f"[{progress_bar}] {percentage:.0f}%",
        f"Transferred: {format_bytes(transferred)} / {format_bytes(total)}",
        f"Speed: {speed_text}",
        f"ETA: {eta_text}",
    )

    for line in lines:
        print(f"\033[2K\r{line}", flush=True)
