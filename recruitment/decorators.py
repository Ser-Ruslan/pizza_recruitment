from functools import wraps
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from .models import UserRole

# Decorator to check if user is an HR manager
def hr_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        # Более простая проверка без исключений
        is_hr = False
        if hasattr(request.user, 'profile'):
            # Используем .value для TextChoices или direct comparison для других типов
            if hasattr(request.user.profile.role, 'value'):
                is_hr = request.user.profile.role.value == UserRole.HR_MANAGER.value
            else:
                is_hr = request.user.profile.role == UserRole.HR_MANAGER
        
        if is_hr or request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        else:
            return HttpResponseForbidden("У вас нет доступа к этой странице")
    
    return wrapper

# Decorator to check if user is a restaurant manager
def restaurant_manager_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        try:
            if request.user.profile.role == UserRole.RESTAURANT_MANAGER or request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            else:
                return HttpResponseForbidden("You don't have permission to access this page.")
        except:
            return HttpResponseForbidden("You don't have permission to access this page.")
    
    return wrapper

# Decorator to check if user is an admin
def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        try:
            if request.user.profile.role == UserRole.ADMIN or request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            else:
                return HttpResponseForbidden("You don't have permission to access this page.")
        except:
            return HttpResponseForbidden("You don't have permission to access this page.")
    
    return wrapper

# Decorator to check if user is a candidate
def candidate_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        try:
            if request.user.profile.role == UserRole.CANDIDATE or request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            else:
                return HttpResponseForbidden("You don't have permission to access this page.")
        except:
            return HttpResponseForbidden("You don't have permission to access this page.")
    
    return wrapper
