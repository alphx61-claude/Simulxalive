"""Typed failures. Every error that reaches a client carries one of these codes."""


class BackendError(Exception):
    """Base for errors that are reportable to a client as a structured event."""

    code = "internal_error"

    def __init__(self, message, *, retry_after=None, detail=None, request_id=None):
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after
        self.detail = detail
        self.request_id = request_id   # echoed back when the command carried one

    def payload(self):
        e = {"code": self.code, "message": self.message}
        if self.retry_after is not None:
            e["retry_after"] = self.retry_after
        if self.detail is not None:
            e["detail"] = self.detail
        return e


class ProtocolError(BackendError):
    """The client sent something the server will not act on."""

    code = "bad_request"


class UnknownCommand(ProtocolError):
    code = "unknown_command"


class UnknownSource(ProtocolError):
    code = "unknown_source"


class UnknownAxis(ProtocolError):
    code = "unknown_axis"


class UnknownJob(ProtocolError):
    code = "unknown_job"


class TooManyJobs(BackendError):
    """Concurrency cap hit; the client should wait for a job to finish."""

    code = "too_many_jobs"


class SourceError(BackendError):
    """An upstream bibliographic API failed."""

    code = "upstream_error"


class SourceRateLimited(SourceError):
    """Upstream asked us to back off for longer than we are willing to wait."""

    code = "upstream_rate_limited"


class SourceUnavailable(SourceError):
    """Upstream could not be reached at all."""

    code = "upstream_unavailable"
