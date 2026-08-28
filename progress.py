import utils


def render_progress(
    filename: str,
    transferred: int,
    total: int,
    elapsed: float,
    first_render: bool,
    session_transferred: int | None = None,
) -> None:
    
    if not first_render:
        print("\033[5F", end="")

    if session_transferred is None:
        session_transferred = transferred

    percentage = (transferred / total) * 100 if total else 100
    bar_width = 20
    filled = min(bar_width, int((percentage / 100) * bar_width))
    progress_bar = "█" * filled + "░" * (bar_width - filled)

    if elapsed > 0 and session_transferred > 0:
        speed = session_transferred / elapsed
        eta = (total - transferred) / speed
        speed_text = f"{utils.format_bytes(int(speed))}/s"
        eta_text = f"{eta:.0f} sec"
    else:
        speed_text = "unavailable"
        eta_text = "unavailable"

    lines = (
        filename,
        f"[{progress_bar}] {percentage:.0f}%",
        f"Transferred: {utils.format_bytes(transferred)} / "
        f"{utils.format_bytes(total)}",
        f"Speed: {speed_text}",
        f"ETA: {eta_text}",
    )

    for line in lines:
        print(f"\033[2K\r{line}", flush=True)
