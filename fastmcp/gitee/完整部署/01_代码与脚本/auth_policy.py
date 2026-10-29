"""Account policy, applied only to identity returned by GitHubProvider."""
ALLOWED_LOGIN = "your-github-login"  # Placeholder: replace with the permitted login in lowercase.


def allowed_identity(token):
    if token is None:
        return None
    claims = getattr(token, "claims", None)
    if not isinstance(claims, dict):
        return None
    login = claims.get("login")
    if not isinstance(login, str) or login.casefold() != ALLOWED_LOGIN:
        return None
    return ALLOWED_LOGIN


def identity_result(token):
    login = allowed_identity(token)
    if login is None:
        raise PermissionError("Access denied")
    return {"status": "ok", "github_login": login}
