import html

_BASE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Alfred MCP</title>
<style>
body {{ font-family: system-ui, sans-serif; background: #111; color: #eee; display: flex;
       align-items: center; justify-content: center; height: 100vh; margin: 0; }}
.card {{ background: #1c1c1c; padding: 2rem; border-radius: 12px; width: 320px; }}
h1 {{ font-size: 1.1rem; margin: 0 0 1rem; }}
p {{ font-size: 0.9rem; color: #aaa; }}
input[type=password] {{ width: 100%; padding: 0.6rem; margin: 0.5rem 0 1rem; border-radius: 6px;
                         border: 1px solid #444; background: #111; color: #eee; box-sizing: border-box; }}
button {{ width: 100%; padding: 0.6rem; border-radius: 6px; border: none; background: #4f7cff;
          color: #fff; font-weight: 600; cursor: pointer; margin-top: 0.4rem; }}
button.deny {{ background: #333; }}
.error {{ color: #ff6b6b; font-size: 0.85rem; margin-bottom: 0.5rem; }}
</style></head>
<body><div class="card">{body}</div></body></html>"""


def login_page(hidden_fields: str, error: str = "") -> str:
    error_html = f'<div class="error">{html.escape(error)}</div>' if error else ""
    body = f"""
    <h1>Sign in to Alfred</h1>
    <p>Approve this app's access to your Alfred assistant.</p>
    {error_html}
    <form method="post" action="/authorize/login">
      {hidden_fields}
      <input type="password" name="password" placeholder="Password" autofocus required>
      <button type="submit">Continue</button>
    </form>
    """
    return _BASE.format(body=body)


def consent_page(client_name: str, hidden_fields: str) -> str:
    safe_name = html.escape(client_name or "This application")
    body = f"""
    <h1>Allow access?</h1>
    <p><strong>{safe_name}</strong> wants to access your Alfred assistant on your behalf
    (tasks, notes, finances, and other data exposed via MCP tools).</p>
    <form method="post" action="/authorize/consent">
      {hidden_fields}
      <button type="submit" name="decision" value="approve">Allow</button>
      <button type="submit" name="decision" value="deny" class="deny">Deny</button>
    </form>
    """
    return _BASE.format(body=body)


def error_page(message: str) -> str:
    body = f'<h1>Error</h1><p>{html.escape(message)}</p>'
    return _BASE.format(body=body)
