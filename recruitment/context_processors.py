from .models import Notification, Test, TestAttempt, UserRole

def notifications_context(request):
    context = {}

    if request.user.is_authenticated:
        # Latest 5 notifications for dropdown
        latest_notifications = Notification.objects.filter(
            user=request.user
        ).order_by('-created_at')[:5]

        # Count of unread notifications
        unread_count = Notification.objects.filter(
            user=request.user,
            read=False
        ).count()

        context.update({
            'latest_notifications': latest_notifications,
            'unread_count': unread_count,
        })

        # Add pending tests count for candidates
        if hasattr(request.user, 'profile') and request.user.profile.role == UserRole.CANDIDATE:
            active_tests = Test.objects.filter(is_active=True)
            passed_tests = TestAttempt.objects.filter(
                user=request.user,
                passed=True,
                test__in=active_tests
            ).values_list('test_id', flat=True)

            pending_tests_count = active_tests.exclude(id__in=passed_tests).count()
            context['pending_tests_count'] = pending_tests_count

    return context