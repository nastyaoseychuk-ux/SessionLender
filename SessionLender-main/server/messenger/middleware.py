from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.utils import timezone

from .models import Profile


class ActiveUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info.rstrip('/') == '/about':
            return self.get_response(request)
        if request.user.is_authenticated:
            profile = Profile.for_user(request.user)
            if profile.is_banned:
                logout(request)
                messages.error(request, 'Ваш акаунт заблоковано адміністратором.')
                return redirect('login')
            Profile.objects.filter(pk=profile.pk).update(last_seen=timezone.now())
        return self.get_response(request)
