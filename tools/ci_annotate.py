"""Print a file's tail as a GitHub Actions error annotation.

Annotations are visible without signing in, unlike job logs.
    python tools/ci_annotate.py TITLE FILE
"""
import sys

title, path = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8", errors="replace").read()[-12000:]
text = text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
print(f"::error title={title}::{text}")
