from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Application, ApplicationComment, Notification, Interview, UserRole, Restaurant
from django.db import transaction

@receiver(post_save, sender=Application)
def application_notifications(sender, instance, created, **kwargs):
    if created:
        vacancy = instance.vacancy
        # Уведомляем HR менеджеров
        from django.contrib.auth import get_user_model
        User = get_user_model()
        hr_users = User.objects.filter(profile__role=UserRole.HR_MANAGER)
        for hr in hr_users:
            Notification.objects.create(
                user=hr,
                title=f"Новая заявка на «{vacancy.title}»",
                message=f"{instance.user.get_full_name()} подал(а) заявку на «{vacancy.title}»."
            )
        
        # Уведомляем менеджеров ресторанов
        for restaurant in vacancy.restaurants.all():
            if restaurant.manager:
                Notification.objects.create(
                    user=restaurant.manager,
                    title=f"Новая заявка на {vacancy.title}",
                    message=f"Поступила заявка от {instance.user.get_full_name()} на «{vacancy.title}».",
                )
    
@receiver(post_save, sender=Interview)
def interview_notifications(sender, instance, created, **kwargs):
    if created:
        user = instance.application.user
        Notification.objects.create(
            user=user,
            title="Собеседование назначено",
            message=(
                f"Для вашей заявки «{instance.application.vacancy.title}» "
                f"назначено собеседование {instance.date_time.strftime('%d.%m.%Y в %H:%M')}."
            )
        )
        if instance.interviewer:
            Notification.objects.create(
                user=instance.interviewer,
                title="Вас назначили интервьюером",
                message=(
                    f"Вас назначили интервьюером для {user.get_full_name()} "
                    f"по вакансии «{instance.application.vacancy.title}» "
                    f"{instance.date_time.strftime('%d.%m.%Y в %H:%M')}."
                )
            )

@receiver(post_save, sender=ApplicationComment)
def comment_notifications(sender, instance, created, **kwargs):
    if created:
        application = instance.application
        author = instance.author
        author_role = author.profile.role if hasattr(author, 'profile') else None

        from django.contrib.auth import get_user_model
        User = get_user_model()

        # Если комментарий от менеджера ресторана, уведомляем HR-менеджеров
        if author_role == UserRole.RESTAURANT_MANAGER:
            hr_users = User.objects.filter(profile__role=UserRole.HR_MANAGER)
            for hr in hr_users:
                Notification.objects.create(
                    user=hr,
                    title=f"Новый комментарий к заявке №{application.id}",
                    message=f"Менеджер ресторана {author.get_full_name()} оставил комментарий к заявке на вакансию «{application.vacancy.title}» от {application.user.get_full_name()}."
                )

        # Если комментарий от HR, уведомляем менеджеров ресторана
        elif author_role == UserRole.HR_MANAGER:
            for restaurant in application.vacancy.restaurants.all():
                if restaurant.manager:
                    Notification.objects.create(
                        user=restaurant.manager,
                        title=f"Комментарий к заявке №{application.id}",
                        message=f"HR-менеджер {author.get_full_name()} оставил комментарий к заявке на вакансию «{application.vacancy.title}» от {application.user.get_full_name()}."
                    )
        