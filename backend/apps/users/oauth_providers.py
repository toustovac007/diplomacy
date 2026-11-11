"""Provider tokens live only in this adapter, never in database records."""
from authlib.integrations.django_client import OAuth
from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

PROVIDERS = ("google", "github")


def enabled(provider):
    return provider in PROVIDERS and all(settings.OAUTH_PROVIDERS[provider].values())


def client_for(provider):
    config = settings.OAUTH_PROVIDERS[provider]
    options = dict(client_id=config["client_id"], client_secret=config["client_secret"],
                   client_kwargs={"scope": "openid email profile" if provider == "google" else "read:user user:email",
                                  "code_challenge_method": "S256", "token_endpoint_auth_method": "client_secret_post",
                                  "default_timeout": 10})
    if provider == "google":
        options["server_metadata_url"] = "https://accounts.google.com/.well-known/openid-configuration"
    else:
        options.update(authorize_url="https://github.com/login/oauth/authorize",
                       access_token_url="https://github.com/login/oauth/access_token",
                       access_token_params={"headers": {"Accept": "application/json"}},
                       api_base_url="https://api.github.com/")
    # Use library protocol primitives with our DB-backed flows, not Django sessions.
    return OAuth().register(provider, **options)


def authorization_url(provider, state, verifier, nonce):
    kwargs = {"state": state, "code_verifier": verifier}
    if nonce:
        kwargs["nonce"] = nonce
    return client_for(provider).create_authorization_url(
        settings.OAUTH_PROVIDERS[provider]["redirect_uri"], **kwargs)["url"]


def verified_identity(flow, code):
    client = client_for(flow.provider)
    token = client.fetch_access_token(code=code, code_verifier=flow.code_verifier,
                                     redirect_uri=settings.OAUTH_PROVIDERS[flow.provider]["redirect_uri"])
    if flow.provider == "google":
        claims = client.parse_id_token(token, nonce=flow.nonce, leeway=30)
        subject = claims["sub"]
        email = claims.get("email") if claims.get("email_verified") is True else None
        username = (email or "player").split("@")[0]
    else:
        response = client.get("user", token=token)
        response.raise_for_status()
        profile = response.json()
        if type(profile.get("id")) is not int or profile["id"] <= 0:
            raise ValueError("Invalid subject")
        subject = str(profile["id"])
        username = profile.get("login", "player")
        response = client.get("user/emails", token=token)
        response.raise_for_status()
        emails = sorted((item for item in response.json() if item.get("verified") is True),
                        key=lambda item: (not item.get("primary", False), item.get("email", "")))
        email = emails[0]["email"] if emails else None
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise ValueError("Invalid subject")
    if email:
        try:
            validate_email(email)
            if len(email) > 254:
                email = None
        except ValidationError:
            email = None
    return {"subject": subject, "email": email, "username": username}
