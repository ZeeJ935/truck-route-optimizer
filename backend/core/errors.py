"""Stable, user-safe service errors.

Each error carries one of the API's stable error codes. Messages never contain
raw provider responses, stack traces, or credentials; details are logged on the
server instead.
"""


class ServiceError(Exception):
    code = "provider_error"
    default_message = "A data provider returned an unexpected response. Please try again."

    def __init__(self, message: str | None = None):
        self.message = message or self.default_message
        super().__init__(self.message)


class ValidationFailed(ServiceError):
    code = "validation_error"
    default_message = "The request is invalid."

    def __init__(self, message: str | None = None, fields: dict[str, str] | None = None):
        super().__init__(message)
        self.fields = dict(fields or {})


class GeocodingFailed(ServiceError):
    code = "geocoding_failed"
    default_message = "The location could not be found."


class NoRouteFound(ServiceError):
    code = "no_route_found"
    default_message = "No truck route was found between these locations."


class ForecastUnavailable(ServiceError):
    code = "forecast_unavailable"
    default_message = "A weather forecast is not available for part of this trip."


class ProviderRateLimited(ServiceError):
    code = "provider_rate_limited"
    default_message = "A data provider is busy. Please wait a minute and try again."


class ProviderTimeout(ServiceError):
    code = "provider_timeout"
    default_message = "A data provider took too long to respond. Please try again."


class ProviderError(ServiceError):
    code = "provider_error"


class RateLimited(ServiceError):
    """This client sent too many requests (our own limit, not a provider's)."""

    code = "rate_limited"
    default_message = "Too many requests. Please wait a minute and try again."

    def __init__(self, message: str | None = None, retry_after_seconds: int = 60):
        super().__init__(message)
        self.retry_after_seconds = max(1, int(retry_after_seconds))


class DailyLimitReached(ServiceError):
    """The app-wide daily budget of weather lookups is used up."""

    code = "daily_limit_reached"
    default_message = (
        "This app has reached its daily weather data limit. Please try again after midnight UTC."
    )


class RequestTooLarge(ServiceError):
    code = "request_too_large"
    default_message = "The request is too large."


class NotFound(ServiceError):
    code = "not_found"
    default_message = "This API endpoint does not exist."


class MethodNotAllowed(ServiceError):
    code = "method_not_allowed"
    default_message = "This HTTP method is not allowed for this endpoint."
