from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def admin_required(view_func):
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        profile = getattr(request.user, 'profile', None)
        if request.user.is_superuser or (profile and profile.is_admin):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'You do not have permission to access that page.')
        return redirect('dashboard:index')

    return _wrapped
