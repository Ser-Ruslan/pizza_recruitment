from .models import Notification, Test, TestAttempt, UserRole

def user_context(request):
    context = {}

    if request.user.is_authenticated:
        # Unread notifications count
        unread_count = Notification.objects.filter(user=request.user, read=False).count()
        context['unread_count'] = unread_count

        # Latest notifications for dropdown
        latest_notifications = Notification.objects.filter(
            user=request.user
        ).order_by('-created_at')[:5]
        context['latest_notifications'] = latest_notifications

        # Tests count for candidates - only for positions they applied to
        if hasattr(request.user, 'profile') and request.user.profile.role == 'CANDIDATE':
            from .models import Test, TestAttempt, Application, QuickApplication

            # Get applications and quick applications for this user
            user_applications = Application.objects.filter(user=request.user)
            quick_applications = QuickApplication.objects.filter(user_created=request.user)

            # Collect position types the user applied for
            applied_position_types = set()

            # From regular applications
            for app in user_applications:
                applied_position_types.add(app.vacancy.position_type.id)

            # From quick applications
            for quick_app in quick_applications:
                applied_position_types.add(quick_app.vacancy.position_type.id)

            if applied_position_types:
                # Get tests for positions user applied to
                available_tests = Test.objects.filter(
                    is_active=True,
                    position_type_id__in=applied_position_types
                )

                # Get passed tests
                passed_tests = TestAttempt.objects.filter(
                    user=request.user,
                    passed=True
                ).values_list('test_id', flat=True)

                pending_tests_count = available_tests.exclude(id__in=passed_tests).count()
                context['pending_tests_count'] = pending_tests_count
            else:
                context['pending_tests_count'] = 0

    return context