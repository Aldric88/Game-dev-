from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app.api.deps import get_storage
from app.core.security import decode_access_token
from app.services.storage import StorageManager

router = APIRouter(prefix="/preview", tags=["preview"])

_FONT_PATCH = """<style>
body, html {
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'SF Pro Text', 'Inter', 'Segoe UI', Helvetica, Arial, sans-serif !important;
  -webkit-font-smoothing: antialiased !important;
  -moz-osx-font-smoothing: grayscale !important;
  text-rendering: optimizeLegibility !important;
}
canvas { image-rendering: auto; }
</style>"""


async def _get_user_from_token(token: str, storage: StorageManager) -> dict | None:
    """Resolve a user from a JWT token string (from query param or header)."""
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub", "")
        return await storage.find_user_by_id(user_id)
    except ValueError:
        return None


def _combine_files_to_html(files: dict[str, str]) -> str:
    """Merge generated files into a single HTML document for rendering."""
    if not files:
        return "<html><body><p>No generated content to preview.</p></body></html>"

    if "index.html" in files:
        html = files["index.html"]
        # Inject font patch before </head>
        if "</head>" in html:
            html = html.replace("</head>", f"{_FONT_PATCH}\n</head>")
        elif "</body>" in html:
            html = html.replace("</body>", f"{_FONT_PATCH}\n</body>")
        return html

    # Build from parts
    css_parts = []
    js_parts = []
    for filename, content in files.items():
        if filename.endswith(".css"):
            css_parts.append(f"<style>/* {filename} */\n{content}\n</style>")
        elif filename.endswith(".js"):
            js_parts.append(f"<script>/* {filename} */\n{content}\n</script>")

    css_block = "\n".join(css_parts)
    js_block = "\n".join(js_parts)
    return (
        f"<!DOCTYPE html><html><head><meta charset='UTF-8'>\n"
        f"{_FONT_PATCH}\n"
        f"{css_block}</head><body>"
        f"{js_block}</body></html>"
    )


@router.get("/public/{project_id}", response_class=HTMLResponse)
async def public_preview_project(
    project_id: str,
    storage: StorageManager = Depends(get_storage),
) -> HTMLResponse:
    """Return the generated game HTML without requiring authentication.

    Allows anyone to view/play a project via a public share link.
    """
    project = await storage.get_project(project_id)
    if not project:
        return HTMLResponse(
            content=(
                "<!DOCTYPE html><html><head><meta charset='UTF-8'>"
                "<title>Not Found</title></head>"
                "<body style='background:#111;color:#888;font-family:system-ui;"
                "display:grid;place-items:center;min-height:100vh'>"
                "<p>Project not found.</p></body></html>"
            ),
            status_code=404,
        )

    generated_code = project.get("generated_code", {})
    if not generated_code:
        return HTMLResponse(
            content=(
                "<html><body style='background:#111;color:#888;font-family:system-ui;"
                "display:grid;place-items:center;min-height:100vh'>"
                "<p>No game generated yet.</p></body></html>"
            )
        )

    files = generated_code.get("files", generated_code)
    html = _combine_files_to_html(files)
    return HTMLResponse(content=html)


@router.get("/{project_id}", response_class=HTMLResponse)
async def preview_project(
    project_id: str,
    request: Request,
    token: str | None = Query(default=None, description="JWT token for iframe auth"),
    storage: StorageManager = Depends(get_storage),
) -> HTMLResponse:
    """Return the generated game HTML for server-side rendered preview.

    Accepts auth token via query param (?token=...) or Authorization header.
    Query param is needed for iframe src since iframes can't send headers.
    """
    # Resolve token from query param or Authorization header
    resolved_token = token
    if not resolved_token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            resolved_token = auth_header[7:]

    if not resolved_token:
        raise HTTPException(status_code=401, detail="Authentication required")

    user = await _get_user_from_token(resolved_token, storage)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")

    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    generated_code = project.get("generated_code", {})
    if not generated_code:
        return HTMLResponse(
            content="<html><body style='background:#111;color:#888;font-family:system-ui;"
            "display:grid;place-items:center;min-height:100vh'>"
            "<p>No game generated yet. Use the prompt to generate one.</p></body></html>"
        )

    files = generated_code.get("files", generated_code)
    html = _combine_files_to_html(files)
    return HTMLResponse(content=html)
