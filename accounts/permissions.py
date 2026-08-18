from functools import wraps
from django.core.exceptions import PermissionDenied
from .models import UserRole

def role_required(*allowed_roles):
    """
    Decorator para restringir acesso a views baseado nas roles do usuário.
    Uso: @role_required(UserRole.MASTER_ADMIN, UserRole.DIRETOR)
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                raise PermissionDenied
            if request.user.is_superuser or request.user.role in allowed_roles:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return _wrapped_view
    return decorator

def master_admin_required(view_func):
    return role_required(UserRole.MASTER_ADMIN)(view_func)

def diretor_required(view_func):
    return role_required(UserRole.MASTER_ADMIN, UserRole.DIRETOR)(view_func)
