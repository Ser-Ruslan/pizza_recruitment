from .models import Notification

def notifications_processor(request):
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(user=request.user, read=False).count()
        latest_notifs = Notification.objects.filter(user=request.user).order_by('-created_at')[:5]
    else:
        unread_count = 0
        latest_notifs = []
    return {
        'unread_count': unread_count,
        'latest_notifications': latest_notifs,
    }