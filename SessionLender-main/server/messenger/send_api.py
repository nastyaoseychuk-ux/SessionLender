import json
import logging
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse, Http404, FileResponse
from django.shortcuts import redirect, get_object_or_404
from django.db import OperationalError, InterfaceError
from .models import Profile
from .security import is_rate_limited
from .sending import store_message, SendError

logger = logging.getLogger(__name__)


@login_required
@require_POST
def send(request, chat_id):
    if not getattr(settings, 'TEST', False) and not getattr(request, '_skip_rate_limit', False):
        if is_rate_limited(
            request,
            'chat_message',
            getattr(settings, 'MESSAGE_RATE_LIMIT', 30),
            getattr(settings, 'MESSAGE_RATE_WINDOW', 60),
        ):
            return JsonResponse(
                {"type": "error", "message": "Забагато повідомлень. Спробуйте пізніше."},
                status=429,
            )
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict) or not data.get("client_nonce"):
            raise SendError("Потрібен ідентифікатор повідомлення.")
        result = store_message(
            request.user, chat_id, data.get("text"), data["client_nonce"]
        )
        return JsonResponse(result)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse(
            {"type": "error", "message": "Некоректний запит."}, status=400
        )
    except SendError as error:
        return JsonResponse(
            {"type": "error", "message": str(error)}, status=error.status
        )
    except (OperationalError, InterfaceError):
        logger.exception("Temporary database failure during send.")
        return JsonResponse(
            {
                "type": "retry",
                "message": "Тимчасово немає зв’язку. Повторюємо надсилання.",
            },
            status=503,
        )


@login_required
def avatar(request, user_id):
    profile = get_object_or_404(Profile, user_id=user_id)
    if not profile.avatar:
        raise Http404
    try:
        response = FileResponse(profile.avatar.open('rb'))
        # Новий аватар зберігається під новим унікальним ім'ям — старе кешується спокійно.
        response['Cache-Control'] = 'private, max-age=3600'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
    except Exception:
        logger.exception("Avatar storage unavailable.")
        raise Http404
