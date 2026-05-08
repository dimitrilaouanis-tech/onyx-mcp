# Publish onyx-paid-mcp to PyPI (1 command + a token)

The wheel + sdist for **v0.2.0** are pre-built in `dist/`. You only need a PyPI API token to upload.

## One-time setup (60 sec)

1. Sign in / register at https://pypi.org/account/register/ (uses email + password OR GitHub OAuth)
2. Go to https://pypi.org/manage/account/token/
3. Create token, scope = "Entire account" (first time) or "Project: onyx-paid-mcp" (subsequent)
4. Copy the token (starts with `pypi-...`)

## Upload (5 sec)

```bash
# In C:\Users\intelligence\onyx_mcp
py -m pip install twine
TWINE_USERNAME=__token__ TWINE_PASSWORD=pypi-YOUR-TOKEN-HERE py -m twine upload dist/onyx_paid_mcp-0.2.0*
```

Or interactively (twine will prompt):
```bash
py -m twine upload dist/onyx_paid_mcp-0.2.0*
# Username: __token__
# Password: pypi-YOUR-TOKEN-HERE
```

Verify after:
```bash
curl -s https://pypi.org/pypi/onyx-paid-mcp/json | py -c "import json,sys; d=json.load(sys.stdin); print('latest:', d['info']['version'])"
# expected: latest: 0.2.0
```

## What this unblocks

- `pip install onyx-paid-mcp` actually works (currently the README claim is aspirational)
- **MCP Registry submission** via `mcp-publisher publish` — registry only hosts metadata, package must be on PyPI/npm/etc first
- Anyone reading dev.to / Show HN / Twitter who wants to try the framework can `pip install` it

## Next-version workflow

When shipping v0.3.0 (next iteration):
1. Bump `pyproject.toml` version
2. `py -m build --wheel --sdist`
3. `py -m twine upload dist/onyx_paid_mcp-0.3.0*`

That's it.
