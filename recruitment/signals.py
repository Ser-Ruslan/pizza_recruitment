from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import (
    Application, ApplicationComment, Notification, Interview, 
    UserRole, Restaurant, QuickApplication, User, UserProfile
)
from django.db import transaction
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings

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
        
@receiver(post_save, sender=QuickApplication)
def quick_application_status_handler(sender, instance, **kwargs):
    if instance.status == 'REVIEWING':
        # Check if user with this email already exists
        if not User.objects.filter(email=instance.email).exists():
            # Create username from full name
            base_username = instance.full_name.lower().replace(' ', '_')
            username = base_username
            counter = 1
            
            # Ensure unique username
            while User.objects.filter(username=username).exists():
                username = f"{base_username}_{counter}"
                counter += 1
            
            # Create user account
            with transaction.atomic():
                user = User.objects.create_user(
                    username=username,
                    email=instance.email,
                    password=User.objects.make_random_password()
                )
                
                # Set full name
                name_parts = instance.full_name.split(maxsplit=1)
                user.first_name = name_parts[0]
                user.last_name = name_parts[1] if len(name_parts) > 1 else ""
                user.save()
                
                # Create profile
                UserProfile.objects.create(
                    user=user,
                    role=UserRole.CANDIDATE,
                    phone=instance.phone
                )
                
                # Create regular application
                Application.objects.create(
                    vacancy=instance.vacancy,
                    user=user,
                    cover_letter=instance.cover_letter,
                    status='REVIEWING'
                )
                
                # Create notification
                # Create notification
                Notification.objects.create(
                    user=user,
                    title="Учетная запись создана",
                    message=f"Для вас была создана учетная запись на основе быстрого отклика на вакансию «{instance.vacancy.title}». Используйте свой email для восстановления пароля."
                )
                
                # Send email with credentials
                import string
                import random
                
                # Generate random password
                chars = string.ascii_letters + string.digits + string.punctuation
                password = ''.join(random.choice(chars) for _ in range(12))
                user.set_password(password)
                user.save()
                
                subject = 'Ваша учетная запись на PizzaJobs'
                message = f'''
                Здравствуйте, {user.get_full_name()}!
                
                Для вас была создана учетная запись на основе быстрого отклика на вакансию «{instance.vacancy.title}».
                
                Данные для входа:
                Логин: {user.username}
                Пароль: {password}
                
                Вы можете войти в систему по адресу: http://127.0.0.1:8000/login/
                
                С уважением,
                Команда PizzaJobs
                '''
                
                try:
                    send_mail(
                        subject,
                        message,
                        settings.DEFAULT_FROM_EMAIL,
                        [user.email],
                        fail_silently=False,
                    )
                except Exception as e:
                    print(f"Failed to send email: {e}")
