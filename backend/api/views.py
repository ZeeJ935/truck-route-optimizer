import logging
import os
import time
import traceback

from django.core.exceptions import RequestDataTooBig
from rest_framework.decorators import api_view
from rest_framework.exceptions import ParseError, UnsupportedMediaType
from rest_framework.request import Request
from rest_framework.response import Response

from analysis.limits import PLACE_SUGGEST_MAX_CHARS, PLACE_SUGGEST_MIN_CHARS
from analysis.request import parse_analysis_request
from core.errors import RequestTooLarge, ServiceError, ValidationFailed

from . import wiring
from .errors import INTERNAL_ERROR_MESSAGE, error_response, internal_error_response
from .presenters import present_analysis
from .throttles import AnalyzePerDayThrottle, AnalyzePerMinuteThrottle, SuggestPerMinuteThrottle, enforce

logger = logging.getLogger(__name__)

__all__ = ["INTERNAL_ERROR_MESSAGE", "analyze_routes", "health", "suggest_places"]


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


def log_unexpected(where: str, error: Exception) -> None:
    """Log the exception type and where it was raised, never its message: messages can
    repeat user-entered places."""
    frames = traceback.extract_tb(error.__traceback__)
    location = " <- ".join(
        f"{os.path.basename(frame.filename)}:{frame.lineno} {frame.name}" for frame in reversed(frames[-5:])
    )
    logger.error("Unexpected %s during %s at %s", type(error).__name__, where, location or "unknown")


@api_view(["POST"])
def analyze_routes(request: Request) -> Response:
    try:
        # Per-client limits come first: no provider is called for a refused request.
        enforce(
            AnalyzePerMinuteThrottle,
            AnalyzePerDayThrottle,
            request=request,
            message="Too many analyses from this device. Please wait a minute and try again.",
        )
        try:
            payload = request.data
        except (ParseError, UnsupportedMediaType):
            raise ValidationFailed("The request body must be valid JSON.") from None
        except RequestDataTooBig:
            raise RequestTooLarge("The request is too large.") from None
        service = wiring.get_analysis_service()
        analysis_request = parse_analysis_request(payload, now=service.now)
        result = service.analyze(analysis_request)
        mark = time.perf_counter()
        body = present_analysis(result)
        serialization = time.perf_counter() - mark
        log_timings(result.stats, serialization)
        return Response(body)
    except ServiceError as error:
        # Only the stable code is logged: messages can quote user-entered places.
        logger.info("Analysis failed with %s.", error.code)
        return error_response(error)
    except Exception as error:
        log_unexpected("route analysis", error)
        return internal_error_response()


@api_view(["GET"])
def suggest_places(request: Request) -> Response:
    """Place suggestions for the origin and destination fields: {"suggestions": [{"label", "type"}]}."""
    try:
        enforce(
            SuggestPerMinuteThrottle,
            request=request,
            message="Too many suggestion requests. You can keep typing the full address.",
        )
        query = " ".join(str(request.query_params.get("q", "")).split())
        if len(query) < PLACE_SUGGEST_MIN_CHARS or len(query) > PLACE_SUGGEST_MAX_CHARS:
            raise ValidationFailed(
                "Search text is too short or too long.",
                fields={"q": f"Enter {PLACE_SUGGEST_MIN_CHARS} to {PLACE_SUGGEST_MAX_CHARS} characters."},
            )
        suggestions = wiring.get_place_suggestion_provider().suggest(query)
    except ServiceError as error:
        logger.info("Place suggestions failed with %s.", error.code)
        return error_response(error)
    except Exception as error:
        log_unexpected("place suggestions", error)
        return internal_error_response()
    return Response({"suggestions": [{"label": item.label, "type": item.kind} for item in suggestions]})
