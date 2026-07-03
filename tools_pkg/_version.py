"""/version — which code is actually serving. Render injects RENDER_GIT_COMMIT
(plus branch/repo) into the env of every deploy, so this endpoint ends the
"is prod stale?" guessing game forever: one GET tells you the exact commit,
branch and repo the live process was built from. No secrets exposed.
"""
import os


def register(app):
    @app.get("/version", include_in_schema=False)
    async def _version():
        return {
            "commit": os.environ.get("RENDER_GIT_COMMIT", "unknown"),
            "branch": os.environ.get("RENDER_GIT_BRANCH", "unknown"),
            "repo": os.environ.get("RENDER_GIT_REPO_SLUG", "unknown"),
            "service": os.environ.get("RENDER_SERVICE_NAME", "local"),
            "hint": "commit=unknown means not running on Render (or an old build predating this endpoint)",
        }
