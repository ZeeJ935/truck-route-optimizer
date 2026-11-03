import logging

from rest_framework.decorators import api_view
from rest_framework.exceptions import APIException, ParseError, UnsupportedMediaType
from rest_framework.request import Request
from rest_framework.response import Response

from analysis.request import parse_analysis_request
from core.errors import ServiceError, ValidationFailed

from . import wiring
from .presenters import present_analysis

logger = logging.getLogger(__name__)

STATUS_BY_CODE = {
    "validation_error": 400,
    "geocoding_failed": 422,
    "no_route_found": 422,
    "forecast_unavailable": 422,
    "provider_rate_limited": 503,
    "provider_timeout": 504,
    "provider_error": 502,
}
RETRY_AFTER_SECONDS = 60
INTERNAL_ERROR_MESSAGE = "Something went wrong while analyzing the trip. Please try again."


def error_response(error: ServiceError) -> Response:
    body = {"code": error.code, "message": error.message}
    if isinstance(error, ValidationFailed) and error.fields:
        body["fields"] = error.fields
    response = Response({"error": body}, status=STATUS_BY_CODE.get(error.code, 500))
    if error.code == "provider_rate_limited":
        response["Retry-After"] = str(RETRY_AFTER_SECONDS)
    return response


@api_view(["GET"])
def health(request: Request) -> Response:
    return Response({"status": "ok"})


@api_view(["POST"])
def analyze_routes(request: Request) -> Response:
    try:
        try:
            payload = request.data
        except (ParseError, UnsupportedMediaType):
            raise ValidationFailed("The request body must be valid JSON.") from None
        service = wiring.get_analysis_service()
        analysis_request = parse_analysis_request(payload, now=service.now)
        result = service.analyze(analysis_request)
        return Response(present_analysis(result))
    except ServiceError as error:
        logger.info("Analysis failed with %s: %s", error.code, error.message)
        return error_response(error)
    except APIException:
        raise
    except Exception:
        logger.exception("Unexpected error during route analysis.")
        return Response({"error": {"code": "internal_error", "message": INTERNAL_ERROR_MESSAGE}}, status=500)
