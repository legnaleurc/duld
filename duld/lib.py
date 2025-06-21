from pathlib import Path


async def compress_to_path(src_path: Path, dst_path: Path, *, base_name: str) -> Path:
    from asyncio import create_subprocess_exec
    from asyncio.subprocess import DEVNULL

    name = f"{base_name}.7z"
    out_path = dst_path / name

    cmd = [
        "7zr",
        "a",
        "-y",
        str(out_path),
        "*",
    ]
    p = await create_subprocess_exec(
        *cmd, cwd=str(src_path), stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL
    )
    rv = await p.wait()
    if rv != 0:
        raise RuntimeError(f"compress error: {src_path}")
    if not out_path.is_file():
        raise RuntimeError(f"compress error: {src_path}")
    return out_path


def is_too_long_to_compress(dst_path: Path, base_name: str) -> bool:
    name = f"{base_name}.7z"
    out_path = dst_path / name
    try:
        out_path.touch()
        out_path.unlink()
        return False
    except OSError as e:
        if e.errno == 36:  # File name too long
            return True
        raise
