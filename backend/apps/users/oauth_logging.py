import logging


class OAuthPrivacyFilter(logging.Filter):
    def filter(self, record):
        if any(path in record.getMessage() for path in ("/oauth/", "/email/verification/", "/verify-email")):
            record.msg = "Authentication HTTP request (URL and query omitted)"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
        return True
