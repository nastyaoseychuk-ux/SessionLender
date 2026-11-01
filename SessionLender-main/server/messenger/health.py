from django.db import connections
from django.db.utils import OperationalError
from django.http import JsonResponse


def health_check(request):
    status = {"status": "ok"}
    try:
        connections["default"].ensure_connection()
        status["db"] = "ok"
    except OperationalError:
        status["db"] = "error"
        status["status"] = "degraded"
    return JsonResponse(status)
