from __future__ import annotations

SKIP_NAMES = {
    ".ds_store",
    "cargo.lock",
    "composer.lock",
    "flake.lock",
    "gemfile.lock",
    "go.sum",
    "package-lock.json",
    "pipfile.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "uv.lock",
    "yarn.lock",
}

SKIP_SUFFIXES = (
    ".7z",
    ".bmp",
    ".class",
    ".css.map",
    ".dll",
    ".dylib",
    ".eot",
    ".exe",
    ".gif",
    ".gz",
    ".icns",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".js.map",
    ".lock",
    ".min.css",
    ".min.js",
    ".min.map",
    ".mp3",
    ".mp4",
    ".o",
    ".otf",
    ".pdf",
    ".png",
    ".pyc",
    ".pyo",
    ".rar",
    ".so",
    ".svg",
    ".tar",
    ".ttf",
    ".wasm",
    ".wav",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
    ".zip",
)

SKIP_DIR_PARTS = {
    ".gradle",
    ".next",
    ".nuxt",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "generated",
    "node_modules",
    "out",
    "pods",
    "site-packages",
    "vendor",
    "venv",
}


def skip_reason(path: str) -> str | None:
    """Return a skip reason for lockfiles, binaries, minified, and generated dirs."""
    posix = path.replace("\\", "/").strip("/")
    if not posix:
        return None
    name = posix.rsplit("/", 1)[-1].lower()
    if name in SKIP_NAMES:
        return f"lockfile/generated ({name})"
    lower = posix.lower()
    for suffix in SKIP_SUFFIXES:
        if lower.endswith(suffix):
            return f"non-source ({suffix})"
    dirs = {part.lower() for part in posix.split("/")[:-1]}
    hit = dirs & SKIP_DIR_PARTS
    if hit:
        folder = sorted(hit)[0]
        return f"generated directory ({folder}/)"
    return None
