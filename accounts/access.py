from functools import wraps

from django.contrib.auth import logout
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden
from django.urls import reverse


def is_administrator(user):
    return user.is_authenticated and user.is_active and (user.is_superuser or user.role == 'ADMINISTRADOR')


def is_operator(user):
    return user.is_authenticated and user.is_active and (user.is_superuser or user.role in {'ADMINISTRADOR', 'PATRULHANTE'})


def operator_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), reverse('accounts:login'))
        if not is_operator(request.user):
            return HttpResponseForbidden('Acesso restrito aos administradores e patrulhantes.')
        return view(request, *args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), reverse('accounts:login'))
        if not is_administrator(request.user):
            return HttpResponseForbidden('Acesso restrito ao administrador.')
        return view(request, *args, **kwargs)
    return wrapped


class OperatorOnlyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not is_operator(request.user):
            logout(request)
        if request.path.startswith('/admin/') and is_operator(request.user) and not is_administrator(request.user):
            return HttpResponseForbidden('Contas e permissões são gerenciadas somente pelo administrador.')
        public = request.path in {reverse('accounts:login'), reverse('accounts:logout'), '/admin/login/'} or request.path.startswith('/static/')
        if not public and not is_operator(request.user):
            return redirect_to_login(request.get_full_path(), reverse('accounts:login'))
        return self.get_response(request)
