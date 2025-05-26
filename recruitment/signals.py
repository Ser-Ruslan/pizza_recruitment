
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import (
    Application, ApplicationComment, Notification, Interview, 
    UserRole, Restaurant, QuickApplication, User, UserProfile, ApplicationStatus, Resume, InterviewStatus
)
from django.db import transaction
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
import string
import random

def send_notification_with_email(user, title, message):
    """
    Creates a notification and sends an email to the user.
    """
    # Create notification
    Notification.objects.create(
        user=user,
        title=title,
        message=message
    )

    # Send email
    send_mail(
        title,
        message,
        settings.EMAIL_HOST_USER,
        [user.email],
        fail_silently=False,
    )

@receiver(post_save, sender=Application)
def application_notifications(sender, instance, created, **kwargs):
    # Проверяем, что это не конвертация из быстрой заявки
    if created and not hasattr(instance, '_from_quick_application'):
        vacancy = instance.vacancy
        # Уведомляем HR менеджеров
        hr_users = User.objects.filter(profile__role=UserRole.HR_MANAGER)
        for hr in hr_users:
            send_notification_with_email(
                hr,
                f"Новая заявка на «{vacancy.title}»",
                f"{instance.user.get_full_name()} подал(а) заявку на «{vacancy.title}»."
            )

        # Уведомляем менеджеров ресторанов
        for restaurant in vacancy.restaurants.all():
            if restaurant.manager:
                send_notification_with_email(
                    restaurant.manager,
                    f"Новая заявка на {vacancy.title}",
                    f"Поступила заявка от {instance.user.get_full_name()} на «{vacancy.title}»."
                )
    
    # Если статус заявки изменился (не создание)
    elif not created:
        # Используем сохранённый старый статус
        old_status = getattr(instance, '_old_status', None)
        
        # Если статус действительно изменился
        if old_status and old_status != instance.status:
                # Обновляем статус связанных собеседований
                interviews = Interview.objects.filter(application=instance)
                
                for interview in interviews:
                    old_interview_status = interview.status
                    
                    # Определяем новый статус собеседования на основе статуса заявки
                    if instance.status == ApplicationStatus.REJECTED:
                        interview.status = InterviewStatus.CANCELLED
                    elif instance.status == ApplicationStatus.ACCEPTED:
                        interview.status = InterviewStatus.COMPLETED
                        interview.completed = True
                    elif instance.status == ApplicationStatus.ON_HOLD:
                        interview.status = InterviewStatus.RESCHEDULED
                    
                    # Сохраняем только если статус изменился
                    if interview.status != old_interview_status:
                        interview.save()
                        
                        # Уведомляем кандидата об изменении статуса собеседования
                        send_notification_with_email(
                            instance.user,
                            f"Статус собеседования изменён",
                            f"Статус вашего собеседования по вакансии «{instance.vacancy.title}» изменён на: {interview.get_status_display()}"
                        )
                        
                        # Уведомляем интервьюера
                        if interview.interviewer:
                            send_notification_with_email(
                                interview.interviewer,
                                f"Статус собеседования изменён",
                                f"Статус собеседования с {instance.user.get_full_name()} по вакансии «{instance.vacancy.title}» изменён на: {interview.get_status_display()}"
                            )
                
                # Уведомляем кандидата об изменении статуса заявки
                send_notification_with_email(
                    instance.user,
                    f"Статус заявки изменён",
                    f"Статус вашей заявки на вакансию «{instance.vacancy.title}» изменён на: {instance.get_status_display()}"
                )

@receiver(post_save, sender=Interview)
def interview_notifications(sender, instance, created, **kwargs):
    if created:
        user = instance.application.user
        send_notification_with_email(
            user,
            "Собеседование назначено",
            f"Для вашей заявки «{instance.application.vacancy.title}» назначено собеседование {instance.date_time.strftime('%d.%m.%Y в %H:%M')}."
        )
        if instance.interviewer:
            send_notification_with_email(
                instance.interviewer,
                "Вас назначили интервьюером",
                f"Вас назначили интервьюером для {user.get_full_name()} по вакансии «{instance.application.vacancy.title}» {instance.date_time.strftime('%d.%m.%Y в %H:%M')}."
            )
    else:
        # Если собеседование обновлено (не создано)
        try:
            # Получаем старый статус из базы данных
            old_interview = Interview.objects.filter(id=instance.id).exclude(id=instance.id).first()
            if old_interview and old_interview.status != instance.status:
                user = instance.application.user
                
                # Уведомляем кандидата
                send_notification_with_email(
                    user,
                    "Обновление по собеседованию",
                    f"Статус вашего собеседования по вакансии «{instance.application.vacancy.title}» изменён на: {instance.get_status_display()}"
                )
                
                # Уведомляем интервьюера
                if instance.interviewer:
                    send_notification_with_email(
                        instance.interviewer,
                        "Обновление по собеседованию",
                        f"Статус собеседования с {user.get_full_name()} по вакансии «{instance.application.vacancy.title}» изменён на: {instance.get_status_display()}"
                    )
                
                # Уведомляем HR менеджеров
                hr_users = User.objects.filter(profile__role=UserRole.HR_MANAGER)
                for hr in hr_users:
                    send_notification_with_email(
                        hr,
                        "Обновление статуса собеседования",
                        f"Статус собеседования с {user.get_full_name()} по вакансии «{instance.application.vacancy.title}» изменён на: {instance.get_status_display()}"
                    )
        except:
            pass

@receiver(post_save, sender=ApplicationComment)
def comment_notifications(sender, instance, created, **kwargs):
    if created:
        application = instance.application
        author = instance.author
        author_role = author.profile.role if hasattr(author, 'profile') else None

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
def quick_application_handler(sender, instance, created, **kwargs):
    if created:
        # Уведомляем HR менеджеров о новой быстрой заявке
        hr_users = User.objects.filter(profile__role=UserRole.HR_MANAGER)
        for hr in hr_users:
            send_notification_with_email(
                hr,
                f"Новый быстрый отклик на {instance.vacancy.title}",
                f"Получен быстрый отклик от {instance.full_name} на вакансию {instance.vacancy.title}."
            )
    
    # Если статус изменился на REVIEWING, создаем аккаунт и обычную заявку
    elif instance.status == ApplicationStatus.REVIEWING:
        # Проверяем, что пользователь еще не существует
        if User.objects.filter(email=instance.email).exists():
            return

        with transaction.atomic():
            # Создаем имя пользователя
            username = instance.full_name.lower().replace(' ', '_')
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{username}_{counter}"
                counter += 1

            # Генерируем пароль
            chars = string.ascii_letters + string.digits + string.punctuation
            password = ''.join(random.choice(chars) for _ in range(12))

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

            # Временно отключаем сигнал
            post_save.disconnect(application_notifications, sender=Application)
            
            # Создаем обычную заявку
            application = Application.objects.create(
                vacancy=instance.vacancy,
                user=user,
                resume=resume,
                cover_letter=instance.cover_letter,
                status=ApplicationStatus.REVIEWING,
                applied_at=instance.created_at
            )
            
            # Восстанавливаем сигнал
            post_save.connect(application_notifications, sender=Application)

            # Отправляем email с данными для входа
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

            # Уведомляем HR менеджеров
            hr_users = User.objects.filter(profile__role=UserRole.HR_MANAGER)
            for hr in hr_users:
                send_notification_with_email(
                    hr,
                    f"Быстрая заявка преобразована в обычную",
                    f"Быстрая заявка от {instance.full_name} на вакансию {instance.vacancy.title} была преобразована в обычную заявку."
                )

            # Уведомляем менеджеров ресторанов
            for restaurant in instance.vacancy.restaurants.all():
                if restaurant.manager:
                    send_notification_with_email(
                        restaurant.manager,
                        f"Быстрая заявка преобразована в обычную",
                        f"Быстрая заявка от {instance.full_name} на вакансию {instance.vacancy.title} была преобразована в обычную заявку."
                    )

            # Удаляем быструю заявку
            instance.delete()

@receiver(pre_save, sender=Application)
def store_old_application_status(sender, instance, **kwargs):
    """Сохраняем старый статус заявки для сравнения в post_save"""
    if instance.pk:
        try:
            old_instance = Application.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except Application.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None
