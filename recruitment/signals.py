from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import (
    Application, ApplicationComment, Notification, Interview, 
    UserRole, Restaurant, QuickApplication, User, UserProfile, ApplicationStatus, Resume, InterviewStatus, Vacancy
)
from django.db import transaction
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
import string
import random

def send_notification_with_email(user, title, message):
    """Отправить уведомление и email"""
    # Создаем уведомление в системе
    Notification.objects.create(
        user=user,
        title=title,
        message=message
    )

    # Отправляем красивый email
    send_mail(
        f'PizzaJobs - {title}',
        '',
        settings.EMAIL_HOST_USER,
        [user.email],
        fail_silently=True,
        html_message=f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 25px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 25px; border-radius: 0 0 10px 10px; }}
                .message-box {{ background: white; padding: 20px; border-radius: 8px; margin: 15px 0; border-left: 4px solid #667eea; }}
                .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🍕 PizzaJobs</h1>
                    <h2>{title}</h2>
                </div>
                <div class="content">
                    <p>Здравствуйте, <strong>{user.get_full_name() or user.username}</strong>!</p>

                    <div class="message-box">
                        <p>{message}</p>
                    </div>

                    <p>Вы можете войти в систему для получения дополнительной информации.</p>

                </div>
                <div class="footer">
                    <p>С уважением,<br><strong>Команда PizzaJobs</strong></p>
                    <p><em>Это автоматическое сообщение, отвечать на него не нужно.</em></p>
                </div>
            </div>
        </body>
        </html>
        '''
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

    # Убираем автоматическое создание заявки из сигналов - теперь это происходит только после прохождения теста

@receiver(post_save, sender=Vacancy)
def vacancy_notifications(sender, instance, created, **kwargs):
    """Уведомления о новых вакансиях для кандидатов"""
    if created and instance.is_active:
        # Находим кандидатов, которые могут быть заинтересованы в этой вакансии
        candidates = User.objects.filter(profile__role=UserRole.CANDIDATE)
        
        for candidate in candidates:
            # Проверяем, подходит ли вакансия профилю кандидата
            profile = candidate.profile
            should_notify = False
            
            # Если у кандидата указана желаемая позиция и она совпадает с типом вакансии
            if profile.desired_position and instance.position_type.title.lower() in profile.desired_position.lower():
                should_notify = True
            
            # Если кандидат уже подавал заявки на похожие вакансии
            elif candidate.applications.filter(vacancy__position_type=instance.position_type).exists():
                should_notify = True
            
            # Если у кандидата есть резюме (активный поиск)
            elif candidate.resumes.filter(is_active=True).exists():
                should_notify = True
            
            if should_notify:
                restaurant_names = ', '.join([r.name for r in instance.restaurants.all()[:3]])
                if instance.restaurants.count() > 3:
                    restaurant_names += f" и ещё {instance.restaurants.count() - 3}"
                
                send_notification_with_email(
                    candidate,
                    f"Новая вакансия: {instance.title}",
                    f"Открыта новая вакансия '{instance.title}' в {restaurant_names}. Возможно, она вам подойдёт!"
                )

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