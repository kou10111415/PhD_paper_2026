"""Rebuild the version-pinned public site without modifying research inputs."""
from pathlib import Path
from latest_site import build_site

if __name__ == "__main__":
    repo = Path(__file__).resolve().parents[1]
    build_site(repo.parent, repo)
