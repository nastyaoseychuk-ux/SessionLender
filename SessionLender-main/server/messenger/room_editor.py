from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from .forms import RoomForm
from .models import Room


@login_required
@require_http_methods(['GET', 'POST'])
def edit_room(request, room_id):
    room = get_object_or_404(Room, pk=room_id)
    if not room.is_owner(request.user):
        raise PermissionDenied
    form = RoomForm(request.POST or None, request.FILES or None, instance=room)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Зміни кімнати збережено.')
        return redirect('room-detail', room.pk)
    return render(request, 'room_edit.html', {'room': room, 'form': form},
                  status=400 if request.method == 'POST' else 200)
