import logging
import time

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


def log_timings(stats, serialization_seconds: float) -> None:
    """One line per analysis with stage timings and counts. No place names, URLs, or keys."""
    stages = " ".join(
        f"{stage}={stats.timings.get(stage, 0.0):.2f}s"
        for stage in ("geocoding", "routing", "via", "weather", "risk", "ranking")
    )
    logger.info(
        "analysis timings: %s serialization=%.2fs total=%.2fs routes=%d via_attempts=%d weather_locations=%d",
        stages,
        serialization_seconds,
        stats.elapsed_seconds + serialization_seconds,
        stats.final_route_count,
        stats.via_attempts,
        stats.weather_locations,
    )


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
        mark = time.perf_counter()
        body = present_analysis(result)
        serialization = time.perf_counter() - mark
        log_timings(result.stats, serialization)
        return Response(body)
    except ServiceError as error:
        logger.info("Analysis failed with %s: %s", error.code, error.message)
        return error_response(error)
    except APIException:
        raise
    except Exception:
        logger.exception("Unexpected error during route analysis.")
        return Response({"error": {"code": "internal_error", "message": INTERNAL_ERROR_MESSAGE}}, status=500)
