from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from .decorators import admin_required
from .forms import AdminSetPasswordForm, LoginForm, UserCreateForm, UserEditForm
from .models import ActivityLog, Profile


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard:index')

    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        auth_login(request, user)
        if not form.cleaned_data.get('remember_me'):
            request.session.set_expiry(0)
        ActivityLog.log(user, 'User logged in', request=request)
        messages.success(request, f'Welcome back, {user.get_full_name() or user.username}!')
        next_url = request.GET.get('next') or request.POST.get('next')
        return redirect(next_url or 'dashboard:index')
    return render(request, 'auth/login.html', {'form': form})


@login_required
def logout_view(request):
    ActivityLog.log(request.user, 'User logged out', request=request)
    auth_logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('accounts:login')


@login_required
def password_change_view(request):
    form = PasswordChangeForm(user=request.user, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        ActivityLog.log(request.user, 'Password changed', request=request)
        messages.success(request, 'Your password has been updated.')
        return redirect('dashboard:index')
    return render(request, 'auth/password_change.html', {'form': form})


@admin_required
def user_list(request):
    query = request.GET.get('q', '').strip()
    users = User.objects.select_related('profile').all().order_by('-date_joined')
    if query:
        from django.db.models import Q
        users = users.filter(
            Q(username__icontains=query) | Q(email__icontains=query) |
            Q(first_name__icontains=query) | Q(last_name__icontains=query)
        )
    paginator = Paginator(users, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'accounts/user_list.html', {'page_obj': page_obj, 'query': query})


@admin_required
def user_create(request):
    form = UserCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        ActivityLog.log(request.user, 'User created', obj=user, description=user.username, request=request)
        messages.success(request, f'User "{user.username}" created successfully.')
        return redirect('accounts:user_list')
    return render(request, 'accounts/user_form.html', {'form': form, 'is_create': True})


@admin_required
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    profile, _ = Profile.objects.get_or_create(user=user)
    initial = {'role': profile.role, 'phone': profile.phone}
    form = UserEditForm(request.POST or None, instance=user, initial=initial)
    if request.method == 'POST' and form.is_valid():
        form.save()
        ActivityLog.log(request.user, 'User updated', obj=user, description=user.username, request=request)
        messages.success(request, f'User "{user.username}" updated successfully.')
        return redirect('accounts:user_list')
    return render(request, 'accounts/user_form.html', {'form': form, 'is_create': False, 'target_user': user})


@admin_required
def user_toggle_active(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, 'You cannot deactivate your own account.')
        return redirect('accounts:user_list')
    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])
    ActivityLog.log(request.user, 'User status toggled', obj=user, description=f'active={user.is_active}', request=request)
    messages.success(request, f'User "{user.username}" is now {"active" if user.is_active else "inactive"}.')
    return redirect('accounts:user_list')


@admin_required
def user_reset_password(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = AdminSetPasswordForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user.set_password(form.cleaned_data['new_password1'])
        user.save()
        ActivityLog.log(request.user, 'Password reset by admin', obj=user, description=user.username, request=request)
        messages.success(request, f'Password reset for "{user.username}".')
        return redirect('accounts:user_list')
    return render(request, 'accounts/user_reset_password.html', {'form': form, 'target_user': user})


@admin_required
def user_delete(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, 'You cannot delete your own account.')
        return redirect('accounts:user_list')
    if request.method == 'POST':
        username = user.username
        user.delete()
        ActivityLog.log(request.user, 'User deleted', description=username, request=request)
        messages.success(request, f'User "{username}" deleted.')
        return redirect('accounts:user_list')
    return render(request, 'accounts/user_confirm_delete.html', {'target_user': user})


@admin_required
def activity_log_list(request):
    logs = ActivityLog.objects.select_related('user').all()

    query = request.GET.get('q', '').strip()
    if query:
        from django.db.models import Q
        logs = logs.filter(
            Q(action__icontains=query) | Q(description__icontains=query) |
            Q(user__username__icontains=query) | Q(object_type__icontains=query)
        )

    paginator = Paginator(logs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'accounts/activity_log_list.html', {'page_obj': page_obj, 'query': query})
