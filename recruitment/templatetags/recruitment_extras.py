
from django import template
from ..models import TestAttempt

register = template.Library()

@register.filter
def has_passed_test(user, test):
    """Check if user has passed the given test"""
    if not user.is_authenticated or not test:
        return False
    return TestAttempt.objects.filter(
        user=user, 
        test=test, 
        passed=True
    ).exists()

@register.filter
def get_passed_attempt(user, test):
    """Get user's passed attempt for the given test"""
    if not user.is_authenticated or not test:
        return None
    return TestAttempt.objects.filter(
        user=user, 
        test=test, 
        passed=True
    ).first()

@register.filter
def get_latest_attempt(user, test):
    """Get user's latest attempt for the given test"""
    if not user.is_authenticated or not test:
        return None
    return TestAttempt.objects.filter(
        user=user, 
        test=test
    ).order_by('-start_time').first()
