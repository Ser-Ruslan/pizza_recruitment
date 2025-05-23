from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from .models import (
    Application, ApplicationComment, Notification, Interview, 
    UserRole, Restaurant, QuickApplication, UserProfile, ApplicationStatus, Resume
)
from django.db import transaction
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
import string
import random

User = get_user_model()

def send_notification_with_email(user, title, message, send_email=True):
    """
    Creates a notification and optionally sends an email to the user.
    """
    # Create notification
    Notification.objects.create(
        user=user,
        title=title,
        message=message
    )

    # Send email only if requested
    if send_email:
        send_mail(
            title,
            message,
            settings.EMAIL_HOST_USER,
            [user.email],
            fail_silently=False,
        )

@receiver(post_save, sender=Application)
def application_notifications(sender, instance, created, **kwargs):
    # Skip notifications for applications converted from quick applications
    if hasattr(instance, '_from_quick_application'):
        # Send only welcome notification for converted applications
        if created:
            send_notification_with_email(
                instance.user,
                "Добро пожаловать в PizzaJobs",
                f"Для вас создан аккаунт. Ваша заявка на вакансию {instance.vacancy.title} принята в работу."
            )
        return
        
    if created:
        vacancy = instance.vacancy
        # Уведомляем HR менеджеров
        hr_users = User.objects.filter(profile__role=UserRole.HR_MANAGER)
        for hr in hr_users:
            send_notification_with_email(
                hr,
                f"Новая заявка на «{vacancy.title}»",
                f"{instance.user.get_full_name()} подал(а) заявку на «{vacancy.title}».",
                send_email=False
            )

        # Уведомляем менеджеров ресторанов
        for restaurant in vacancy.restaurants.all():
            if restaurant.manager:
                send_notification_with_email(
                    restaurant.manager,
                    f"Новая заявка на {vacancy.title}",
                    f"Поступила заявка от {instance.user.get_full_name()} на «{vacancy.title}»."
                )

@receiver(post_save, sender=Interview)
def interview_notifications(sender, instance, created, **kwargs):
    if created:
        user = instance.application.user
        send_notification_with_email(
            user,
            "Собеседование назначено",
            (
                f"Для вашей заявки «{instance.application.vacancy.title}» "
                f"назначено собеседование {instance.date_time.strftime('%d.%m.%Y в %H:%M')}."
            )
        )
        if instance.interviewer:
            send_notification_with_email(
                instance.interviewer,
                "Вас назначили интервьюером",
                (
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
                send_notification_with_email(
                    hr,
                    f"Новый комментарий к заявке №{application.id}",
                    f"Менеджер ресторана {author.get_full_name()} оставил комментарий к заявке на вакансию «{application.vacancy.title}» от {application.user.get_full_name()}."
                )

        # Если комментарий от HR, уведомляем менеджеров ресторана
        elif author_role == UserRole.HR_MANAGER:
            for restaurant in application.vacancy.restaurants.all():
                if restaurant.manager:
                    send_notification_with_email(
                        restaurant.manager,
                        f"Комментарий к заявке №{application.id}",
                        f"HR-менеджер {author.get_full_name()} оставил комментарий к заявке на вакансию «{application.vacancy.title}» от {application.user.get_full_name()}."
                    )

@receiver(post_save, sender=QuickApplication)
def quick_application_status_handler(sender, instance, created, **kwargs):
    # Создаем уведомления для HR при создании быстрой заявки
    if created:
        # Уведомляем HR менеджеров
        hr_users = User.objects.filter(profile__role=UserRole.HR_MANAGER)
        for hr in hr_users:
            send_notification_with_email(
                hr,
                f"Новый быстрый отклик на {instance.vacancy.title}",
                f"Получен быстрый отклик от {instance.full_name} на вакансию {instance.vacancy.title}."
            )

    # Этот сигнал вызывается, когда меняется статус быстрой заявки
    if not created and instance.status == ApplicationStatus.REVIEWING:
        # Логика конвертации быстрой заявки в обычную
        # Создаем имя пользователя на основе полного имени
        username = instance.full_name.lower().replace(' ', '_')
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{username}_{counter}"
            counter += 1

        # Вместо User.objects.make_random_password() используем собственную генерацию
        # Генерируем случайный пароль
        chars = string.ascii_letters + string.digits + string.punctuation
        password = ''.join(random.choice(chars) for _ in range(12))

        with transaction.atomic():
            # Создаем пользователя
            user = User.objects.create_user(
                username=username,
                email=instance.email,
                password=password
            )

            # Устанавливаем имя
            name_parts = instance.full_name.split(maxsplit=1)
            user.first_name = name_parts[0]
            user.last_name = name_parts[1] if len(name_parts) > 1 else ''
            user.save()

            # Создаем профиль
            UserProfile.objects.create(
                user=user,
                role=UserRole.CANDIDATE,
                phone=instance.phone
            )

            # Создаем резюме
            resume = Resume.objects.create(
                user=user,
                title=f"Резюме от {instance.created_at.strftime('%d.%m.%Y')}",
                file=instance.resume,
                is_active=True
            )

            # Создаем обычную заявку
            application = Application.objects.create(
                vacancy=instance.vacancy,
                user=user,
                resume=resume,
                cover_letter=instance.cover_letter,
                status=ApplicationStatus.REVIEWING,
                applied_at=instance.created_at
            )

            # Отправляем email
            send_mail(
                'Ваша заявка принята в работу - PizzaJobs',
                f'''Здравствуйте, {instance.full_name}!

                Ваша заявка на вакансию "{instance.vacancy.title}" принята в работу.

                Для вас создан аккаунт на сайте PizzaJobs:
                Логин: {username}
                Пароль: {password}

                Пожалуйста, войдите в систему и заполните свой профиль.
                ''',
                settings.EMAIL_HOST_USER,
                [instance.email],
                fail_silently=False,
            )

            # Создаем уведомление для кандидата
            send_notification_with_email(
                user,
                "Добро пожаловать в PizzaJobs",
                f"Для вас создан аккаунт. Ваша заявка на вакансию {instance.vacancy.title} принята в работу."
            )