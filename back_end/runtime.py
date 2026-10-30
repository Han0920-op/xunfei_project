"""Public release/protocol identifiers, no environment values or credentials."""
from fastapi.staticfiles import StaticFiles

APP_VERSION = "2026.10.30.1"
STREAM_PROTOCOL = "zhimai-chat-sse-v2"


class FrontendFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if path.endswith((".html", ".js", ".css")) or path in ("", "."):
            # Revalidate app code after deployment; keep photo caching untouched.
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
            response.headers["X-Zhimai-Version"] = APP_VERSION
        return response
