"""One JSON error envelope for every API response: {"error": {"code", "message", "fields"?}}."""

from __future__ import annotations

from django.http import JsonResponse
from rest_framework import exceptions as drf
from rest_framework.response import Response

from core.errors import MethodNotAllowed, NotFound, RateLimited, ServiceError, ValidationFailed

STATUS_BY_CODE = {
    "validation_error": 400,
    "not_found": 404,
    "method_not_allowed": 405,
    "request_too_large": 413,
    "geocoding_failed": 422,
    "no_route_found": 422,
    "forecast_unavailable": 422,
    "rate_limited": 429,
    "provider_error": 502,
    "provider_rate_limited": 503,
    "daily_limit_reached": 503,
    "provider_timeout": 504,
}
PROVIDER_RETRY_AFTER_SECONDS = 60
INTERNAL_ERROR_MESSAGE = "Something went wrong. Please try again."


def error_body(error: ServiceError) -> dict:
    body = {"code": error.code, "message": error.message}
    if isinstance(error, ValidationFailed) and error.fields:
        body["fields"] = error.fields
    return {"error": body}


def error_response(error: ServiceError) -> Response:
    response = Response(error_body(error), status=STATUS_BY_CODE.get(error.code, 500))
    if isinstance(error, RateLimited):
        response["Retry-After"] = str(error.retry_after_seconds)
    elif error.code == "provider_rate_limited":
        response["Retry-After"] = str(PROVIDER_RETRY_AFTER_SECONDS)
    return response


def internal_error_response() -> Response:
    return Response({"error": {"code": "internal_error", "message": INTERNAL_ERROR_MESSAGE}}, status=500)


def drf_exception_handler(exc, context):
    """DRF errors raised outside our views' own handling (e.g. 405) use the same envelope."""
    if isinstance(exc, drf.MethodNotAllowed):
        return error_response(MethodNotAllowed())
    if isinstance(exc, (drf.ParseError, drf.UnsupportedMediaType)):
        return error_response(ValidationFailed("The request body must be valid JSON."))
    if isinstance(exc, drf.NotFound):
        return error_response(NotFound())
    if isinstance(exc, drf.Throttled):
        return error_response(RateLimited(retry_after_seconds=int(exc.wait or 60)))
    if isinstance(exc, drf.APIException):
        status = exc.status_code
        return Response({"error": {"code": "request_error", "message": "The request could not be processed."}}, status=status)
    return None  # unexpected: Django's 500 handler below


def json_not_found(request, exception=None):
    return JsonResponse(error_body(NotFound()), status=404)


def json_server_error(request):
    return JsonResponse({"error": {"code": "internal_error", "message": INTERNAL_ERROR_MESSAGE}}, status=500)
