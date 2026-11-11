import logging


class OAuthPrivacyFilter(logging.Filter):
    def filter(self, record):
        if "/oauth/" in record.getMessage():
            record.msg = "OAuth HTTP request (URL and query omitted)"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
        return True
