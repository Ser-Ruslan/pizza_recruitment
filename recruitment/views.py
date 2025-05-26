from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate, logout
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Q, F, Case, When, Value, FloatField, Avg
from django.db.models.functions import Round
from .models import QuickApplication, Vacancy, ApplicationStatus
from django.http import HttpResponseForbidden, JsonResponse
from django.core.paginator import Paginator
from django.utils import timezone
from django.urls import reverse
from django.db import transaction
from django.core.mail import send_mail
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Application, ApplicationStatus, QuickApplication, UserProfile, UserRole, Notification, Resume
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
import string
import random
import json  # Import json

from .models import (
    User, UserProfile, Resume, Restaurant, PositionType, 
    Vacancy, Application, Interview, ApplicationComment, 
    Notification, UserRole, ApplicationStatus, Test,
    TestAttempt, Question, Answer, UserAnswer, InterviewStatus
)
from .forms import (
    UserRegisterForm, UserProfileForm, ResumeUploadForm, 
    VacancyForm, ApplicationForm, ApplicationStatusForm, 
    InterviewForm, ApplicationCommentForm, QuickApplicationForm,
    HRCandidateCreationForm, ApplyCandidateForm
)
from .decorators import (
    hr_required, restaurant_manager_required, 
    admin_required, candidate_required
)

# Home view
def home(request):
    # Get counts for statistics
    vacancy_count = Vacancy.objects.filter(is_active=True).count()
    restaurant_count = Restaurant.objects.count()
    position_types = PositionType.objects.all()[:5]  # Get 5 position types for display

    # Get recent vacancies with statistics
    recent_vacancies = Vacancy.objects.filter(is_active=True).annotate(
        total_applications=Count('applications', distinct=True),
        accepted_applications=Count(
            'applications',
            filter=Q(applications__status=ApplicationStatus.ACCEPTED),
            distinct=True
        ),
    ).annotate(
        acceptance_rate=Round(
            Case(
                When(total_applications__gt=0,
                    then=F('accepted_applications') * Value(100.0) / F('total_applications')),
                default=Value(0),
                output_field=FloatField()
            ),
            0
        )
    ).order_by('-created_at')[:3]

    context = {
        'vacancy_count': vacancy_count,
        'restaurant_count': restaurant_count,
        'position_types': position_types,
        'recent_vacancies': recent_vacancies,
    }
    return render(request, 'home.html', context)

# Registration view
def register(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()

            # Create user profile
            UserProfile.objects.create(
                user=user,
                role=UserRole.CANDIDATE
            )

            # Log in the user
            login(request, user)
            messages.success(request, 'Учетная запись успешно создана! Пожалуйста, заполните свой профиль.')
            return redirect('edit_profile')
    else:
        form = UserRegisterForm()

    return render(request, 'registration/register.html', {'form': form})

# User profile views
@login_required
def view_profile(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    resumes = Resume.objects.filter(user=request.user, is_active=True)

    # Get applications if user is a candidate
    applications = []
    if user_profile.role == UserRole.CANDIDATE:
        applications = Application.objects.filter(user=request.user).order_by('-applied_at')

    context = {
        'profile': user_profile,
        'resumes': resumes,
        'applications': applications,
    }
    return render(request, 'profile/view.html', context)

@login_required
def edit_profile(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)

    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=user_profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Профиль успешно обновлен.')
            return redirect('view_profile')
    else:
        form = UserProfileForm(instance=user_profile)

    return render(request, 'profile/edit.html', {'form': form})

# Resume management
@login_required
def upload_resume(request):
    # Check if user is a candidate
    if not hasattr(request.user, 'profile') or request.user.profile.role != UserRole.CANDIDATE:
        return HttpResponseForbidden("You don't have permission to access this page.")

    if request.method == 'POST':
        form = ResumeUploadForm(request.POST, request.FILES)
        if form.is_valid():
            resume = form.save(commit=False)
            resume.user = request.user

            try:
                resume.clean()  # Run validation
                resume.save()
                messages.success(request, 'Резюме успешно загружено.')
                return redirect('view_profile')
            except ValueError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, 'There was an error uploading your resume.')
    else:
        form = ResumeUploadForm()

    return render(request, 'profile/upload_resume.html', {'form': form})

@login_required
@candidate_required
def delete_resume(request, resume_id):
    resume = get_object_or_404(Resume, id=resume_id, user=request.user)

    if request.method == 'POST':
        resume.is_active = False
        resume.save()
        messages.success(request, 'Резюме успешно удалено.')
        return redirect('view_profile')

    return render(request, 'profile/delete_resume.html', {'resume': resume})

# Vacancy views
def vacancy_list(request):
    # Get filter parameters
    city = request.GET.get('city', '')
    position_type = request.GET.get('position_type', '')
    restaurant_id = request.GET.get('restaurant', '')

    # Start with all active vacancies
    vacancies = Vacancy.objects.filter(is_active=True)

    # Apply filters
    if city:
        vacancies = vacancies.filter(restaurants__city=city)

    if position_type:
        vacancies = vacancies.filter(position_type__title=position_type)

    if restaurant_id:
        vacancies = vacancies.filter(restaurants__id=restaurant_id)

    vacancies = vacancies.annotate(
        total_applications=Count('applications', distinct=True),
        accepted_applications=Count(
            'applications',
            filter=Q(applications__status=ApplicationStatus.ACCEPTED),
            distinct=True
        ),
    ).annotate(
        # Вычисляем (accepted_applications * 100 / total_applications) и округляем до 0 знаков
        acceptance_rate=Round(
           Case(
               When(total_applications__gt=0,
                     then=F('accepted_applications') * Value(100.0) / F('total_applications')),
                default=Value(0),
                output_field=FloatField()
            ),
            0
        )
    )

    # Get unique cities and position types for filter dropdowns
    cities = Restaurant.objects.values_list('city', flat=True).distinct()
    position_types = PositionType.objects.all()
    restaurants = Restaurant.objects.all()

    # Paginate results
    paginator = Paginator(vacancies.distinct(), 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'cities': cities,
        'position_types': position_types,
        'restaurants': restaurants,
        'selected_city': city,
        'selected_position_type': position_type,
        'selected_restaurant': restaurant_id,
    }
    return render(request, 'vacancies/list.html', context)

def vacancy_detail(request, vacancy_id):
        vacancy = get_object_or_404(Vacancy, id=vacancy_id, is_active=True)

        user_applied = False
        if request.user.is_authenticated:
            user_applied = Application.objects.filter(
                vacancy=vacancy,
                user=request.user
            ).exists()

        total_applications = Application.objects.filter(vacancy=vacancy).count()
        accepted_applications = Application.objects.filter(
            vacancy=vacancy,
            status=ApplicationStatus.ACCEPTED
        ).count()

        acceptance_rate = (
            (accepted_applications * 100) // total_applications
            if total_applications > 0 else 0
        )

        vacancy_restaurants = vacancy.restaurants.all()


        similar_qs = (Vacancy.objects
        .filter(is_active=True,
                restaurants__in=vacancy_restaurants)
        .exclude(pk=vacancy.pk)
        .distinct())

        restaurant_ids = vacancy_restaurants.values_list('id', flat=True)
        similar_vacancies = []
        for sim in similar_qs.prefetch_related('restaurants'):
            common = sim.restaurants.filter(id__in=restaurant_ids).first()
            similar_vacancies.append({
                'vacancy': sim,
                'restaurant': common
                })

        context = {
            'vacancy': vacancy,
            'user_applied': user_applied,
            'total_applications': total_applications,
            'acceptance_rate': acceptance_rate,
            'similar_vacancies': similar_vacancies,
        }
        return render(request, 'vacancies/detail.html', context)


# Application views
@login_required
@candidate_required
def apply_for_vacancy(request, vacancy_id):
    vacancy = get_object_or_404(Vacancy, id=vacancy_id, is_active=True)

    # Check if user has already applied
    if Application.objects.filter(vacancy=vacancy, user=request.user).exists():
        messages.warning(request, 'Вы уже подали заявку на эту должность.')
        return redirect('vacancy_detail', vacancy_id=vacancy_id)

    # Get user's active resumes
    resumes = Resume.objects.filter(user=request.user, is_active=True)
    if not resumes.exists():
        messages.warning(request, 'Пожалуйста загрузите резюме.')
        return redirect('upload_resume')

    if request.method == 'POST':
        form = ApplicationForm(request.POST, user=request.user)
        if form.is_valid():
            # Check if test is required for this position
            position_test = vacancy.position_type.test
            if position_test and position_test.is_active:
                test_passed = TestAttempt.objects.filter(
                    test=position_test,
                    user=request.user,
                    passed=True
                ).exists()

                if not test_passed:
                    # Store application data in session and redirect to test
                    request.session['application_data'] = {
                        'vacancy_id': vacancy.id,
                        'resume_id': form.cleaned_data['resume'].id,
                        'cover_letter': form.cleaned_data['cover_letter']
                    }
                    messages.info(request, 'Данные сохранены. Теперь необходимо пройти тест для этой позиции.')
                    return redirect('take_test', test_id=position_test.id)

            # No test required or test already passed - create application
            application = form.save(commit=False)
            application.vacancy = vacancy
            application.user = request.user
            application.save()

            # Notifications will be handled by signals

            messages.success(request, 'Ваша заявка успешно отправлена.')
            return redirect('vacancy_detail', vacancy_id=vacancy_id)
    else:
        form = ApplicationForm(user=request.user)

    context = {
        'form': form,
        'vacancy': vacancy,
    }
    return render(request, 'applications/apply.html', context)

@login_required
def application_list(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)

    # Different views based on role
    if user_profile.role == UserRole.CANDIDATE:
        # Candidates see their own applications
        applications = Application.objects.filter(user=request.user).order_by('-applied_at')
        quick_applications = []
        show_quick_applications = False

    elif user_profile.role == UserRole.HR_MANAGER:
        # HR managers see all applications
        applications = Application.objects.all().order_by('-applied_at')
        quick_applications = QuickApplication.objects.all().order_by('-created_at')
        show_quick_applications = True

    elif user_profile.role == UserRole.RESTAURANT_MANAGER:
        # Restaurant managers see applications for their restaurant's vacancies
        managed_restaurants = Restaurant.objects.filter(manager=request.user)
        applications = Application.objects.filter(
            vacancy__restaurants__in=managed_restaurants
        ).distinct().order_by('-applied_at')
        quick_applications = QuickApplication.objects.filter(
            vacancy__restaurants__in=managed_restaurants
        ).distinct().order_by('-created_at')
        show_quick_applications = True

    else:
        # Admin sees all applications
        applications = Application.objects.all().order_by('-applied_at')
        quick_applications = QuickApplication.objects.all().order_by('-created_at')

    # Apply filters
    status_filter = request.GET.get('status', '')
    if status_filter:
        applications = applications.filter(status=status_filter)
        # Если выбраны новые заявки и их нет, но есть быстрые отклики
        if status_filter == 'NEW' and not applications.exists() and quick_applications.filter(status='NEW').exists():
            messages.info(request, 'Обычных новых заявок нет, но есть быстрые отклики')
            return redirect('quick_applications')

    vacancy_filter = request.GET.get('vacancy', '')
    if vacancy_filter:
        applications = applications.filter(vacancy__id=vacancy_filter)

    # Paginate results
    paginator = Paginator(applications, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Get vacancies for filter dropdown
    if user_profile.role == UserRole.RESTAURANT_MANAGER:
        vacancies = Vacancy.objects.filter(restaurants__manager=request.user)
    else:
        vacancies = Vacancy.objects.all()

    # Check if there are new quick applications
    has_new_quick_applications = QuickApplication.objects.filter(status=ApplicationStatus.NEW).exists()

    context = {
        'page_obj': page_obj,
        'statuses': ApplicationStatus.choices,
        'vacancies': vacancies,
        'selected_status': status_filter,
        'selected_vacancy': vacancy_filter,
        'has_new_quick_applications': has_new_quick_applications,
    }
    return render(request, 'applications/list.html', context)

@login_required
@login_required
@require_http_methods(["POST"])
def delete_comment(request, comment_id):
    comment = get_object_or_404(ApplicationComment, id=comment_id)

    # Check permissions
    if not (request.user == comment.author or 
            request.user.profile.role in [UserRole.HR_MANAGER, UserRole.RESTAURANT_MANAGER]):
        return HttpResponseForbidden("У вас нет прав для удаления этого комментария.")

    application_id = comment.application.id
    comment.delete()
    messages.success(request, "Комментарий удален.")
    return redirect('application_detail', application_id=application_id)

@login_required
@require_http_methods(["POST"])
def moderate_comment(request, comment_id):
    if not request.user.profile.role in [UserRole.HR_MANAGER, UserRole.RESTAURANT_MANAGER]:
        return HttpResponseForbidden("У вас нет прав для модерации комментариев.")

    comment = get_object_or_404(ApplicationComment, id=comment_id)
    action = request.POST.get('action')

    if action == 'approve':
        comment.is_approved = True
        comment.needs_moderation = False
        messages.success(request, "Комментарий одобрен.")
    elif action == 'reject':
        comment.delete()
        messages.success(request, "Комментарий отклонен.")

    comment.save()
    return redirect('application_detail', application_id=comment.application.id)

def application_detail(request, application_id):
    # Get the application, with different access rules based on role
    application = get_object_or_404(Application, id=application_id)
    user_profile = get_object_or_404(UserProfile, user=request.user)

    # Check permissions
    if user_profile.role == UserRole.CANDIDATE:
        # Candidates can only view their own applications
        if application.user != request.user:
            return HttpResponseForbidden("You don't have permission to view this application.")

    elif user_profile.role == UserRole.RESTAURANT_MANAGER:
        # Managers can only see applications for their restaurants
        manager_restaurants = Restaurant.objects.filter(manager=request.user)
        application_restaurants = application.vacancy.restaurants.all()
        if not any(r in manager_restaurants for r in application_restaurants):
            return HttpResponseForbidden("You don't have permission to view this application.")

    # Get related data
    # Only show comments to HR managers, restaurant managers and admins
    if user_profile.role in [UserRole.HR_MANAGER, UserRole.RESTAURANT_MANAGER, UserRole.ADMIN]:
        comments = ApplicationComment.objects.filter(application=application).order_by('created_at')
    else:
        comments = []
    
    interviews = Interview.objects.filter(application=application).order_by('date_time')

    # Forms
    status_form = None
    comment_form = None
    interview_form = None

    # Only HR and restaurant managers can update status and add comments
    if user_profile.role in [UserRole.HR_MANAGER, UserRole.RESTAURANT_MANAGER, UserRole.ADMIN]:
        status_form = ApplicationStatusForm(instance=application)
        comment_form = ApplicationCommentForm()

        # Process status form submission
        if request.method == 'POST' and 'update_status' in request.POST:
            # Сохраняем старый статус ДО создания формы и обновления
            old_status = application.status

            status_form = ApplicationStatusForm(request.POST, instance=application)
            if status_form.is_valid():
                updated_application = status_form.save()

                # Create notification for candidate если статус изменился
                if old_status != updated_application.status:
                    Notification.objects.create(
                        user=updated_application.user,
                        title="Обновлён статус заявки",
                        message=f"Статус вашей заявки на {updated_application.vacancy.title} изменился на: {updated_application.get_status_display()}"
                    )

                messages.success(request, 'Статус заявки обновлён.')
                return redirect('application_detail', application_id=application.id)

        # Process comment form submission (only for HR and managers)
        elif request.method == 'POST' and 'add_comment' in request.POST:
            comment_form = ApplicationCommentForm(request.POST)
            if comment_form.is_valid():
                comment = comment_form.save(commit=False)
                comment.application = application
                comment.author = request.user
                comment.save()  # Сигнал post_save срабатывает здесь и создает уведомления

                messages.success(request, 'Комментарий успешно добавлен.')
                return redirect('application_detail', application_id=application.id)

    # Only HR can schedule interviews
    if user_profile.role == UserRole.HR_MANAGER:
        interview_form = InterviewForm(application=application)

        # Process interview form submission
        if request.method == 'POST' and 'schedule_interview' in request.POST:
            interview_form = InterviewForm(request.POST, application=application)
            if interview_form.is_valid():
                interview = interview_form.save(commit=False)
                interview.application = application
                interview.scheduled_by = request.user
                interview.save()

                # Update application status only if it's not already interview scheduled
                if application.status != ApplicationStatus.INTERVIEW_SCHEDULED:
                    application.status = ApplicationStatus.INTERVIEW_SCHEDULED
                    application.save()

                # Create notification for candidate
                Notification.objects.create(
                    user=application.user,
                    title="Собеседование назначено",
                    message=f"Для вашей заявки на вакансию '{application.vacancy.title}' назначено собеседование на {interview.date_time.strftime('%d.%m.%Y в %H:%M')}."
                )

                # Create notification for interviewer if assigned
                if interview.interviewer and interview.interviewer != request.user:
                    Notification.objects.create(
                        user=interview.interviewer,
                        title="Вас назначили интервьюером",
                        message=f"Вас назначили интервьюером для {application.user.get_full_name()} по вакансии '{application.vacancy.title}' на {interview.date_time.strftime('%d.%m.%Y в %H:%M')}."
                    )

                messages.success(request, 'Собеседование успешно назначено.')
                return redirect('application_detail', application_id=application.id)

    context = {
        'application': application,
        'comments': comments,
        'interviews': interviews,
        'status_form': status_form,
        'comment_form': comment_form,
        'interview_form': interview_form,
    }
    return render(request, 'applications/detail.html', context)

# HR Dashboard views
def get_trend_data():
    """Получить данные трендов для различных периодов"""
    from datetime import datetime, timedelta
    from django.utils import timezone

    now = timezone.now()
    periods = {
        'current': now,
        '1_week': now - timedelta(weeks=1),
        '2_weeks': now - timedelta(weeks=2), 
        '1_month': now - timedelta(days=30),
        '2_months': now - timedelta(days=60),
        '6_months': now - timedelta(days=180),
        '1_year': now - timedelta(days=365)
    }

    trend_data = {}

    for period_name, period_date in periods.items():
        # Вакансии на момент периода
        vacancies_total = Vacancy.objects.filter(created_at__lte=period_date).count()
        vacancies_active = Vacancy.objects.filter(created_at__lte=period_date, is_active=True).count()

        # Заявки за период
        applications_total = Application.objects.filter(applied_at__lte=period_date).count()
        applications_new = Application.objects.filter(applied_at__lte=period_date, status='NEW').count()
        # Принятые заявки: ACCEPTED + INTERVIEW_SCHEDULED + REJECTED (все обработанные)
        applications_accepted = Application.objects.filter(
            applied_at__lte=period_date, 
            status__in=['ACCEPTED', 'INTERVIEW_SCHEDULED', 'REJECTED']
        ).count()

        # Быстрые заявки за период
        quick_apps_total = QuickApplication.objects.filter(created_at__lte=period_date).count()
        quick_apps_new = QuickApplication.objects.filter(created_at__lte=period_date, status='NEW').count()

        # Интервью за период - все заявки со статусом INTERVIEW_SCHEDULED
        interviews_total = Application.objects.filter(
            applied_at__lte=period_date, 
            status='INTERVIEW_SCHEDULED'
        ).count()
        interviews_scheduled = Application.objects.filter(
            applied_at__lte=period_date, 
            status='INTERVIEW_SCHEDULED'
        ).count()
        # Добавляем реальные завершенные интервью
        interviews_completed = Interview.objects.filter(
            date_time__lte=period_date, 
            status='COMPLETED'
        ).count()

        # Тесты за период
        test_attempts = TestAttempt.objects.filter(start_time__lte=period_date).count()
        test_passed = TestAttempt.objects.filter(start_time__lte=period_date, passed=True).count()
        test_success_rate = (test_passed * 100 / test_attempts) if test_attempts > 0 else 0

        trend_data[period_name] = {
            'vacancies_total': vacancies_total,
            'vacancies_active': vacancies_active,
            'applications_total': applications_total,
            'applications_new': applications_new,
            'applications_accepted': applications_accepted,
            'quick_apps_total': quick_apps_total,
            'quick_apps_new': quick_apps_new,
            'interviews_total': interviews_total,
            'interviews_scheduled': interviews_scheduled,
            'interviews_completed': interviews_completed,
            'test_attempts': test_attempts,
            'test_passed': test_passed,
            'test_success_rate': test_success_rate
        }

    return trend_data

def calculate_trend_percentage(current, previous):
    """Вычислить процент изменения между периодами"""
    if previous == 0:
        return 100 if current > 0 else 0
    return round(((current - previous) / previous) * 100, 1)

@login_required
@hr_required
def hr_dashboard(request):
        # Проверка роли через профиль
        try:
            user_profile = request.user.profile
            if user_profile.role not in ['HR_MANAGER', 'ADMIN']:
                messages.error(request, 'У вас нет доступа к этой странице.')
                return redirect('dashboard')
        except UserProfile.DoesNotExist:
            messages.error(request, 'Профиль пользователя не найден.')
            return redirect('dashboard')

        # === СТАТИСТИКА ПО ВАКАНСИЯМ ===
        total_vacancies = Vacancy.objects.count()
        active_vacancies = Vacancy.objects.filter(is_active=True).count()

        vacancies_by_status = (
            Vacancy.objects
            .values('is_active')
            .annotate(count=Count('id'))
            .order_by('is_active')
        )

        # === СТАТИСТИКА ПО ОТКЛИКАМ ===
        # Обычные отклики
        total_applications = Application.objects.count()
        new_regular_applications = Application.objects.filter(status='NEW').count()  # ИЗМЕНЕНО

        applications_by_status = (
            Application.objects
            .values('status')
            .annotate(count=Count('id'))
            .order_by('status')
        )

        # Быстрые отклики
        total_quick_applications = QuickApplication.objects.count()
        new_quick_applications = QuickApplication.objects.filter(status='NEW').count()

        # Общие отклики
        total_all_applications = total_applications + total_quick_applications
        new_applications = new_regular_applications + new_quick_applications  # ИЗМЕНЕНО

        # Интервью
        interviews_scheduled = Application.objects.filter(status='INTERVIEW_SCHEDULED').count()
        
        # Получаем все интервью для подсчета
        all_interviews = Interview.objects.all()
        total_interviews_count = all_interviews.count()
        
        # Запланированные интервью (только будущие)
        upcoming_interviews = Interview.objects.filter(
            date_time__gte=timezone.now(),
            status__in=['SCHEDULED', 'CONFIRMED']
        ).select_related('application__user', 'application__vacancy', 'interviewer').order_by('date_time')[:10]
        
        # Завершенные интервью (учитываем все завершенные и проведенные)
        completed_interviews = Interview.objects.filter(
            Q(status='COMPLETED') | Q(date_time__lt=timezone.now())
        ).count()
        
        # Интервью в процессе или завершенные
        processed_interviews = Interview.objects.filter(
            status__in=['COMPLETED', 'IN_PROGRESS', 'CONFIRMED']
        ).count()

        # === НЕДАВНИЕ ОТКЛИКИ ===
        recent_applications = (
            Application.objects
            .select_related('user', 'vacancy')
            .order_by('-applied_at')[:10]
        )

        # === СТАТИСТИКА ТЕСТИРОВАНИЯ ===
        test_attempts = TestAttempt.objects.all()
        total_attempts = test_attempts.count()
        passed_attempts = test_attempts.filter(passed=True).count()
        success_rate = (passed_attempts * 100 / total_attempts) if total_attempts > 0 else 0

        # Статистика по компетенциям
        competency_stats = []
        position_types = PositionType.objects.filter(test__isnull=False, test__is_active=True).distinct()

        for position_type in position_types:
            attempts = TestAttempt.objects.filter(test=position_type.test)
            total = attempts.count()
            passed = attempts.filter(passed=True).count()
            avg_score = attempts.aggregate(Avg('score'))['score__avg'] or 0
            success_rate_comp = (passed * 100 / total) if total > 0 else 0

            competency_stats.append({
                'position_type': position_type.title,
                'total_attempts': total,
                'passed_attempts': passed,
                'success_rate': success_rate_comp,
                'avg_score': avg_score,
            })

        test_statistics = {
            'total_attempts': total_attempts,
            'passed_attempts': passed_attempts,
            'success_rate': success_rate,
            'competency_stats': competency_stats,
        }

        # === ДАННЫЕ ТРЕНДОВ ===
        trend_data = get_trend_data()

        # Текущие данные для сравнения
        current = {
            'vacancies_total': total_vacancies,
            'vacancies_active': active_vacancies,
            'applications_total': total_all_applications,
            'applications_new': new_applications,
            'applications_accepted': Application.objects.filter(
                status__in=['ACCEPTED', 'INTERVIEW_SCHEDULED', 'REJECTED']
            ).count(),
            'quick_apps_total': total_quick_applications,
            'interviews_total': Application.objects.filter(status='INTERVIEW_SCHEDULED').count(),
            'test_success_rate': success_rate
        }

        # Вычисляем тренды для каждого периода
        trends = {}
        for period in ['1_week', '2_weeks', '1_month', '2_months', '6_months', '1_year']:
            period_data = trend_data[period]
            trends[period] = {
                'vacancies_total': calculate_trend_percentage(current['vacancies_total'], period_data['vacancies_total']),
                'vacancies_active': calculate_trend_percentage(current['vacancies_active'], period_data['vacancies_active']),
                'applications_total': calculate_trend_percentage(current['applications_total'], period_data['applications_total']),
                'applications_new': calculate_trend_percentage(current['applications_new'], period_data['applications_new']),
                'applications_accepted': calculate_trend_percentage(current['applications_accepted'], period_data['applications_accepted']),
                'quick_apps_total': calculate_trend_percentage(current['quick_apps_total'], period_data['quick_apps_total']),
                'interviews_total': calculate_trend_percentage(current['interviews_total'], period_data['interviews_total']),
                'test_success_rate': calculate_trend_percentage(current['test_success_rate'], period_data['test_success_rate'])
            }

        # Добавляем отладочную информацию
        print("=== DEBUG TRENDS DATA ===")
        print("Current data:", current)
        print("Trend data keys:", trend_data.keys())
        print("Trends:", trends)
        print("===========================")

        context = {
            # Статистика вакансий
            'total_vacancies': total_vacancies,
            'active_vacancies': active_vacancies,
            'vacancies_by_status': vacancies_by_status,

            # Статистика откликов
            'total_applications': total_applications,
            'total_all_applications': total_all_applications,
            'total_quick_applications': total_quick_applications,
            'new_regular_applications': new_regular_applications,  # ИЗМЕНЕНО
            'new_quick_applications': new_quick_applications,
            'new_applications': new_applications,
            'applications_by_status': applications_by_status,

            # Прочая статистика
            'recent_applications': recent_applications,
            'interviews_scheduled': interviews_scheduled,
            'processed_applications': Application.objects.filter(
                status__in=['ACCEPTED', 'INTERVIEW_SCHEDULED', 'REJECTED']
            ).count(),
            'test_statistics': test_statistics,
            
            # Статистика интервью
            'upcoming_interviews': upcoming_interviews,
            'total_interviews_count': total_interviews_count,
            'completed_interviews': completed_interviews,
            'processed_interviews': processed_interviews,

            # Данные трендов (сериализуем в JSON)
            'trend_data': json.dumps(trend_data),
            'trends': json.dumps(trends),
        }

        return render(request, 'hr/dashboard.html', context)

@login_required
@hr_required
def manage_vacancies(request):
    vacancies = Vacancy.objects.all().order_by('-created_at')

    # Фильтрация
    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        vacancies = vacancies.filter(is_active=True)
    elif status_filter == 'inactive':
        vacancies = vacancies.filter(is_active=False)

    position_filter = request.GET.get('position_type', '')
    if position_filter:
        vacancies = vacancies.filter(position_type__id=position_filter)

    # Пагинация
    paginator = Paginator(vacancies, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Статистика
    total = Vacancy.objects.count()
    active = Vacancy.objects.filter(is_active=True).count()
    inactive = total - active

    # Типы позиций для фильтра
    position_types = PositionType.objects.all()

    context = {
        'page_obj': page_obj,
        'position_types': position_types,
        'selected_status': status_filter,
        'selected_position_type': position_filter,
        # новые переменные
        'total_vacancies': total,
        'active_vacancies': active,
        'inactive_vacancies': inactive,
    }
    return render(request, 'hr/vacancies_list.html', context)

@login_required
@hr_required
def create_vacancy(request):
    if request.method == 'POST':
        form = VacancyForm(request.POST)
        if form.is_valid():
            vacancy = form.save(commit=False)
            vacancy.created_by = request.user
            vacancy.save()

            # Save many-to-many relationships
            form.save_m2m()

            messages.success(request, 'Вакансия создана успешно.')
            return redirect('manage_vacancies')
    else:
        form = VacancyForm()

    context = {
        'form': form,
        'action': 'Create',
    }
    return render(request, 'hr/vacancy_form.html', context)

@login_required
@restaurant_manager_required
def create_vacancy_manager(request):
    if request.method == 'POST':
        form = VacancyForm(request.POST)
        if form.is_valid():
            vacancy = form.save(commit=False)
            vacancy.created_by = request.user
            vacancy.is_active = False  # Создается неактивной по умолчанию
            vacancy.save()

            # Ограничиваем рестораны только теми, которыми управляет менеджер
            managed_restaurants = Restaurant.objects.filter(manager=request.user)
            selected_restaurants = form.cleaned_data['restaurants'].filter(id__in=managed_restaurants.values_list('id', flat=True))
            vacancy.restaurants.set(selected_restaurants)

            # Уведомляем HR менеджеров о новой вакансии
            hr_users = User.objects.filter(profile__role=UserRole.HR_MANAGER)
            restaurant_names = ', '.join([r.name for r in selected_restaurants.all()])

            for hr in hr_users:
                Notification.objects.create(
                    user=hr,
                    title=f'Новая вакансия от менеджера ресторана',
                    message=f'Менеджер {request.user.get_full_name()} создал новую вакансию "{vacancy.title}" для ресторанов: {restaurant_names}. Требуется одобрение.'
                )

            messages.success(request, 'Вакансия создана и отправлена на одобрение HR менеджеру.')
            return redirect('manager_dashboard')
    else:
        # Создаем форму только с ресторанами, которыми управляет менеджер
        form = VacancyForm()
        managed_restaurants = Restaurant.objects.filter(manager=request.user)
        form.fields['restaurants'].queryset = managed_restaurants

        if not managed_restaurants.exists():
            messages.error(request, 'Вы не управляете ни одним рестораном. Обратитесь к администратору.')
            return redirect('manager_dashboard')

    context = {
        'form': form,
        'action': 'Create',
        'is_manager': True,
    }
    return render(request, 'manager/vacancy_form.html', context)

@login_required
@hr_required
def edit_vacancy(request, vacancy_id):
    vacancy = get_object_or_404(Vacancy, id=vacancy_id)

    if request.method == 'POST':
        form = VacancyForm(request.POST, instance=vacancy)
        if form.is_valid():
            form.save()
            messages.success(request, 'Вакансия обновлена успешно.')
            return redirect('manage_vacancies')
    else:
        form = VacancyForm(instance=vacancy)

    context = {
        'form': form,
        'vacancy': vacancy,
        'action': 'Edit',
    }
    return render(request, 'hr/vacancy_form.html', context)

@login_required
@hr_required
def toggle_vacancy_status(request, vacancy_id):
    vacancy = get_object_or_404(Vacancy, id=vacancy_id)
    if request.method == 'POST':
        vacancy.is_active = not vacancy.is_active
        vacancy.save()

        # Уведомление всем, кто подавал на эту вакансию
        status_text = "активирована" if vacancy.is_active else "деактивирована"
        for app in vacancy.applications.all():
            Notification.objects.create(
                user=app.user,
                title=f"Вакансия «{vacancy.title}» {status_text}",
                message=f"Вакансия, на которую вы подавали заявку, была {status_text}."
            )

        messages.success(request, f'Вакансия успешно {status_text}.')
    return redirect('manage_vacancies')


# Restaurant Manager Dashboard views
@login_required
@restaurant_manager_required
def manager_dashboard(request):
    # Get statistics for the manager's restaurants
    managed_restaurants = Restaurant.objects.filter(manager=request.user)

    # Recent applications for manager's restaurants
    recent_applications = Application.objects.filter(
        vacancy__restaurants__in=managed_restaurants
    ).distinct().order_by('-applied_at')[:10]

    # Scheduled interviews
    upcoming_interviews = Interview.objects.filter(
        Q(interviewer=request.user) | 
        Q(application__vacancy__restaurants__in=managed_restaurants),
        date_time__gte=timezone.now()
    ).distinct().order_by('date_time')[:5]

    # Applications by status
    applications_by_status = Application.objects.filter(
        vacancy__restaurants__in=managed_restaurants
    ).values('status').annotate(count=Count('id'))

    context = {
        'managed_restaurants': managed_restaurants,
        'recent_applications': recent_applications,
        'upcoming_interviews': upcoming_interviews,
        'applications_by_status': applications_by_status,
    }
    return render(request, 'manager/dashboard.html', context)

# Notification views
@login_required
def notifications(request):
    qs = Notification.objects.filter(user=request.user).order_by('-created_at')

    if request.method == 'POST':
        if 'delete' in request.POST:
            Notification.objects.filter(id=request.POST['delete'], user=request.user).delete()
            messages.success(request, 'Уведомление удалено.')
            return redirect('notifications')
        elif 'mark_all_read' in request.POST:
            qs.filter(read=False).update(read=True)
            messages.success(request, 'Все уведомления отмечены как прочитанные.')
            return redirect('notifications')
        elif 'mark_read' in request.POST:
            notification_id = request.POST.get('mark_read')
            notification = get_object_or_404(Notification, id=notification_id, user=request.user)
            notification.read = True
            notification.save()
            messages.success(request, 'Уведомление отмечено как прочитанное.')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'success'})
            return redirect('notifications')

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
        'unread_count': qs.filter(read=False).count(),
    }
    return render(request, 'notifications/list.html', context)

# Logout view
@require_http_methods(["GET", "POST"])
def quick_apply(request, vacancy_id):
    vacancy = get_object_or_404(Vacancy, id=vacancy_id, is_active=True)

    if request.method == 'POST':
        form = QuickApplicationForm(request.POST, request.FILES)
        if form.is_valid():
            quick_app = form.save(commit=False)
            quick_app.vacancy = vacancy
            quick_app.save()

            # Create notifications for HR and restaurant managers
            for restaurant in vacancy.restaurants.all():
                if restaurant.manager:
                    Notification.objects.create(
                        user=restaurant.manager,
                        title=f"Быстрый отклик на {vacancy.title}",
                        message=f"Получен быстрый отклик от {quick_app.full_name} на вакансию {vacancy.title}."
                    )

            # Send welcome email to candidate
            send_mail(
                'Добро пожаловать в PizzaJobs - Ваш отклик отправлен!',
                f'''Здравствуйте, {quick_app.full_name}!

Добро пожаловать в PizzaJobs! 

Ваш быстрый отклик на вакансию "{vacancy.title}" успешно отправлен и ожидает рассмотрения HR-менеджера.

Мы свяжемся с вами в ближайшее время для дальнейших шагов.

С уважением,
Команда PizzaJobs''',
                settings.EMAIL_HOST_USER,
                [quick_app.email],
                fail_silently=False,
            )

            messages.success(request, 'Ваш быстрый отклик успешно отправлен. HR-менеджер рассмотрит вашу заявку.')
            return redirect('vacancy_detail', vacancy_id=vacancy_id)
    else:
        form = QuickApplicationForm()

    context = {
        'form': form,
        'vacancy': vacancy,
    }
    return render(request, 'vacancies/quick_apply.html', context)

@login_required
def quick_applications(request):
    user_profile = request.user.profile

    if user_profile.role == UserRole.HR_MANAGER:
        quick_apps = QuickApplication.objects.all()
    elif user_profile.role == UserRole.RESTAURANT_MANAGER:
        managed_restaurants = Restaurant.objects.filter(manager=request.user)
        quick_apps = QuickApplication.objects.filter(
            vacancy__restaurants__in=managed_restaurants
        ).distinct()
    else:
        return HttpResponseForbidden("У вас нет доступа к этой странице.")

    # Check if users exist for quick applications
    for app in quick_apps:
        app.user_exists = User.objects.filter(email=app.email).exists()

    quick_apps = quick_apps.order_by('-created_at')
    context = {
        'quick_applications': quick_apps,
        'application_statuses': ApplicationStatus.choices,
    }
    return render(request, 'hr/quick_applications.html', context)

@login_required
@require_http_methods(["POST"])
def update_quick_application_status(request, app_id):
    quick_app = get_object_or_404(QuickApplication, id=app_id)

    # Check if user already exists
    if User.objects.filter(email=quick_app.email).exists():
        messages.error(request, "Невозможно изменить статус, так как для этой заявки уже создан аккаунт.")
        return redirect('quick_applications')

    new_status = request.POST.get('status')
    if new_status in dict(ApplicationStatus.choices):
        quick_app.status = new_status
        quick_app.save()
        messages.success(request, "Статус быстрой заявки обновлен.")

    return redirect('quick_applications')

@login_required
@require_http_methods(["POST"])
def delete_quick_application(request, app_id):
    quick_app = get_object_or_404(QuickApplication, id=app_id)
    quick_app.delete()
    messages.success(request, "Быстрая заявка удалена.")
    return redirect('quick_applications')

@login_required
@hr_required
def convert_quick_application(request, app_id):
    if request.method == 'POST':
        quick_app = get_object_or_404(QuickApplication, id=app_id, status=ApplicationStatus.NEW)

        # Check if user already exists
        if User.objects.filter(email=quick_app.email).exists():
            messages.error(request, "Пользователь с таким email уже существует.")
            return redirect('quick_applications')

        # Create user account
        username = quick_app.email.split('@')[0]
        if User.objects.filter(username=username).exists():
            username = f"{username}_{random.randint(1000, 9999)}"

        password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))

        user = User.objects.create_user(
            username=username,
            email=quick_app.email,
            password=password,
            first_name=quick_app.full_name.split()[0] if quick_app.full_name.split() else quick_app.full_name,
            last_name=' '.join(quick_app.full_name.split()[1:]) if len(quick_app.full_name.split()) > 1 else ''
        )

        # Create user profile
        UserProfile.objects.create(
            user=user,
            role=UserRole.CANDIDATE,
            phone=quick_app.phone
        )

        # Generate test token if test is required
        position_test = quick_app.vacancy.position_type.test
        if position_test and position_test.is_active:
            test_token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
            quick_app.test_token = test_token

        quick_app.status = ApplicationStatus.REVIEWING
        quick_app.user_created = user
        quick_app.save()

        # Send email with credentials and test link
        if position_test and position_test.is_active:
            test_link = request.build_absolute_uri(reverse('take_test_by_token', args=[test_token]))
            send_mail(
                'Ваша заявка рассмотрена - Создан аккаунт PizzaJobs',
                f'''Здравствуйте, {quick_app.full_name}!

Ваша быстрая заявка на вакансию "{quick_app.vacancy.title}" была рассмотрена HR-менеджером.

Для вас создан аккаунт на сайте PizzaJobs:
Логин: {username}
Пароль: {password}

Для продолжения процесса отбора вам необходимо пройти тест.
Ссылка для прохождения теста: {test_link}

После успешного прохождения теста ваша заявка будет направлена на дальнейшее рассмотрение.

С уважением,
Команда PizzaJobs''',
                settings.EMAIL_HOST_USER,
                [quick_app.email],
                fail_silently=False,
            )
        else:
            send_mail(
                'Ваша заявка рассмотрена - Создан аккаунт PizzaJobs',
                f'''Здравствуйте, {quick_app.full_name}!

Ваша быстрая заявка на вакансию "{quick_app.vacancy.title}" была рассмотрена HR-менеджером.

Для вас создан аккаунт на сайте PizzaJobs:
Логин: {username}
Пароль: {password}

Теперь вы можете войти в систему и отслеживать статус своей заявки.

С уважением,
Команда PizzaJobs''',
                settings.EMAIL_HOST_USER,
                [quick_app.email],
                fail_silently=False,
            )

        messages.success(request, f'Аккаунт создан для {quick_app.full_name}. Данные: Логин: {username}, Пароль: {password}. Email отправлен.')

        return redirect('quick_applications')

    return HttpResponseNotAllowed(['POST'])

def logout_view(request):
    if request.method == 'POST':
        logout(request)
        messages.success(request, 'Вы успешно вышли из системы')
        return redirect('home')
    return render(request, 'registration/logout.html')
@login_required
@hr_required
def select_position_for_test(request):
    # Получаем все типы позиций, у которых еще нет тестов
    position_types_without_tests = PositionType.objects.filter(test__isnull=True)

    context = {
        'position_types': position_types_without_tests,
    }
    return render(request, 'hr/select_position_for_test.html', context)

@login_required
@hr_required
def create_test(request, position_type_id):
    position_type = get_object_or_404(PositionType, id=position_type_id)

    if request.method == 'POST':
        test = Test.objects.create(
            position_type=position_type,
            title=request.POST['title'],
            description=request.POST['description'],
            time_limit=request.POST['time_limit'],
            passing_score=request.POST['passing_score']
        )

        questions_data = json.loads(request.POST['questions'])
        for q_data in questions_data:
            question = Question.objects.create(
                test=test,
                text=q_data['text'],
                points=q_data['points']
            )
            for a_data in q_data['answers']:
                Answer.objects.create(
                    question=question,
                    text=a_data['text'],
                    is_correct=a_data['is_correct']
                )

        messages.success(request, 'Тест успешно создан')
        return redirect('manage_tests')

    return render(request, 'hr/create_test.html', {'position_type': position_type})

def take_test(request, test_id):
    test = get_object_or_404(Test, id=test_id)

    # For non-authenticated users (quick apply), redirect to login/register
    if not request.user.is_authenticated:
        request.session['test_id'] = test_id
        messages.warning(request, 'Для прохождения теста необходимо зарегистрироваться.')
        return redirect('register')

    # Check if user already passed the test
    if TestAttempt.objects.filter(test=test, user=request.user, passed=True).exists():
        messages.warning(request, 'Вы уже успешно прошли этот тест')
        # Handle session data for redirects
        quick_app_id = request.session.get('quick_app_id')
        application_data = request.session.get('application_data')

        if quick_app_id:
            del request.session['quick_app_id']
            quick_app = QuickApplication.objects.get(id=quick_app_id)
            # Send quick application
            for restaurant in quick_app.vacancy.restaurants.all():
                if restaurant.manager:
                    Notification.objects.create(
                        user=restaurant.manager,
                        title=f"Быстрый отклик на {quick_app.vacancy.title}",
                        message=f"Получен быстрый отклик от {quick_app.full_name} на вакансию {quick_app.vacancy.title}."
                    )
            messages.success(request, 'Ваш быстрый отклик успешно отправлен.')
            return redirect('vacancy_detail', vacancy_id=quick_app.vacancy.id)
        elif application_data:
            del request.session['application_data']
            # Create regular application
            application = Application.objects.create(
                vacancy_id=application_data['vacancy_id'],
                user=request.user,
                resume_id=application_data['resume_id'],
                cover_letter=application_data['cover_letter']
            )
            messages.success(request, 'Тест пройден. Ваша заявка успешно отправлена.')
            return redirect('vacancy_detail', vacancy_id=application.vacancy.id)
        else:
            vacancy = Vacancy.objects.filter(position_type=test.position_type, is_active=True).first()
            if vacancy:
                return redirect('vacancy_detail', vacancy_id=vacancy.id)
            else:
                return redirect('vacancy_list')

    if request.method == 'POST':
        attempt = TestAttempt.objects.create(
            test=test,
            user=request.user
        )

        score = 0
        total_points = sum(q.points for q in test.questions.all())

        for question in test.questions.all():
            answer_id = request.POST.get(f'question_{question.id}')
            if answer_id:
                selected_answer = Answer.objects.get(id=answer_id)
                UserAnswer.objects.create(
                    attempt=attempt,
                    question=question,
                    selected_answer=selected_answer
                )
                if selected_answer.is_correct:
                    score += question.points

        attempt.score = (score / total_points) * 100
        attempt.passed = attempt.score >= test.passing_score
        attempt.end_time = timezone.now()
        attempt.save()

        if attempt.passed:
            # Check what type of application this is for
            quick_app_id = request.session.get('quick_app_id')
            application_data = request.session.get('application_data')

            if quick_app_id:
                # Quick application process
                del request.session['quick_app_id']
                quick_app = QuickApplication.objects.get(id=quick_app_id)

                # Send quick application
                for restaurant in quick_app.vacancy.restaurants.all():
                    if restaurant.manager:
                        Notification.objects.create(
                            user=restaurant.manager,
                            title=f"Быстрый отклик на {quick_app.vacancy.title}",
                            message=f"Получен быстрый отклик от {quick_app.full_name} на вакансию {quick_app.vacancy.title}."
                        )

                messages.success(request, f'Поздравляем! Вы успешно прошли тест с результатом {attempt.score:.1f}%. Ваш быстрый отклик отправлен.')
                return redirect('vacancy_detail', vacancy_id=quick_app.vacancy.id)

            elif application_data:
                # Regular application process
                del request.session['application_data']

                # Create the application
                application = Application.objects.create(
                    vacancy_id=application_data['vacancy_id'],
                    user=request.user,
                    resume_id=application_data['resume_id'],
                    cover_letter=application_data['cover_letter']
                )

                messages.success(request, f'Поздравляем! Вы успешно прошли тест с результатом {attempt.score:.1f}%. Ваша заявка отправлена.')
                return redirect('vacancy_detail', vacancy_id=application.vacancy.id)

            else:
                # Direct test taking
                messages.success(request, f'Поздравляем! Вы успешно прошли тест с результатом {attempt.score:.1f}%')
                vacancy = Vacancy.objects.filter(position_type=test.position_type, is_active=True).first()
                if vacancy:
                    messages.info(request, 'Теперь вы можете подать заявку на вакансию')
                    return redirect('apply_for_vacancy', vacancy_id=vacancy.id)
                else:
                    return redirect('vacancy_list')
        else:
            # Test failed
            quick_app_id = request.session.get('quick_app_id')
            application_data = request.session.get('application_data')

            if quick_app_id:
                del request.session['quick_app_id']
                quick_app = QuickApplication.objects.get(id=quick_app_id)
                messages.error(request, f'К сожалению, вы не прошли тест. Ваш результат: {attempt.score:.1f}%. Минимальный проходной балл: {test.passing_score}%')
                return redirect('vacancy_detail', vacancy_id=quick_app.vacancy.id)
            elif application_data:
                del request.session['application_data']
                messages.error(request, f'К сожалению, вы не прошли тест. Ваш результат: {attempt.score:.1f}%. Минимальный проходной балл: {test.passing_score}%')
                return redirect('vacancy_detail', vacancy_id=application_data['vacancy_id'])
            else:
                messages.error(request, f'К сожалению, вы не прошли тест. Ваш результат: {attempt.score:.1f}%. Минимальный проходной балл: {test.passing_score}%')
                vacancy = Vacancy.objects.filter(position_type=test.position_type, is_active=True).first()
                if vacancy:
                    return redirect('vacancy_detail', vacancy_id=vacancy.id)
                else:
                    return redirect('vacancy_list')

    return render(request, 'vacancies/take_test.html', {'test': test})

@login_required
@hr_required
def toggle_test(request, test_id):
    if request.method == 'POST':
        test = get_object_or_404(Test, id=test_id)
        test.is_active = not test.is_active
        test.save()
        status = "активирован" if test.is_active else "деактивирован"
        messages.success(request, f'Тест успешно {status}.')
    return redirect('manage_tests')

@login_required
@hr_required
def manage_tests(request):
    position_types = PositionType.objects.all().prefetch_related('test', 'vacancies')
    return render(request, 'hr/all_tests.html', {'position_types': position_types})

@login_required
@hr_required
def create_tests_for_all_vacancies(request):
    # Создаем тесты для всех типов позиций, у которых нет тестов
    position_types = PositionType.objects.filter(test__isnull=True)

    for position_type in position_types:
        # Создаем базовый тест для каждого типа позиции
        test = Test.objects.create(
            position_type=position_type,
            title=f"Тест для позиции {position_type.title}",
            description=f"Тестирование знаний и навыков для позиции {position_type.title}",
            time_limit=30,
            passing_score=70
        )

        # Создаем базовые вопросы для теста
        questions = [
            {
                "text": f"Опишите ваш опыт работы, связанный с позицией {position_type.title}",
                "points": 30,
                "answers": [
                    {"text": "Имею более 3 лет опыта", "is_correct": True},
                    {"text": "Имею 1-3 года опыта", "is_correct": True},
                    {"text": "Имею менее 1 года опыта", "is_correct": False},
                    {"text": "Не имею опыта", "is_correct": False}
                ]
            },
            {
                "text": "Готовы ли вы работать в команде?",
                "points": 20,
                "answers": [
                    {"text": "Да, имею опыт командной работы", "is_correct": True},
                    {"text": "Предпочитаю работать самостоятельно", "is_correct": False}
                ]
            },
            {
                "text": "Какой график работы вам подходит?",
                "points": 20,
                "answers": [
                    {"text": "Готов(а) к сменному графику", "is_correct": True},
                    {"text": "Только стандартный график", "is_correct": True},
                    {"text": "Не готов(а) к регулярному графику", "is_correct": False}
                ]
            }
        ]

        for q_data in questions:
            question = Question.objects.create(
                test=test,
                text=q_data["text"],
                points=q_data["points"]
            )
            for a_data in q_data["answers"]:
                Answer.objects.create(
                    question=question,
                    text=a_data["text"],
                    is_correct=a_data["is_correct"]
                )

    messages.success(request, f'Тесты успешно созданы для {len(position_types)} типов позиций')
    return redirect('manage_tests')

@login_required
@hr_required
def edit_test(request, test_id):
    test = get_object_or_404(Test, id=test_id)

    if request.method == 'POST':
        test.title = request.POST['title']
        test.description = request.POST['description']
        test.time_limit = request.POST['time_limit']
        test.passing_score = request.POST['passing_score']
        test.save()

        # Delete existing questions and answers
        test.questions.all().delete()

        # Create new questions and answers
        questions_data = json.loads(request.POST['questions'])
        for q_data in questions_data:
            question = Question.objects.create(
                test=test,
                text=q_data['text'],
                points=q_data['points']
            )
            for a_data in q_data['answers']:
                Answer.objects.create(
                    question=question,
                    text=a_data['text'],
                    is_correct=a_data['is_correct']
                )

        messages.success(request, 'Тест успешно обновлен')
        return redirect('manage_tests')

    return render(request, 'hr/edit_test.html', {'test': test})

@login_required
@hr_required
def delete_test(request, test_id):
    if request.method == 'POST':
        test = get_object_or_404(Test, id=test_id)
        test.delete()
        messages.success(request, 'Тест успешно удален')
    return redirect('manage_tests')

def take_test_by_token(request, token):
    quick_app = get_object_or_404(QuickApplication, test_token=token)
    test = quick_app.vacancy.position_type.test

    if not test or not test.is_active:
        messages.error(request, 'Тест для данной позиции не найден или неактивен.')
        return redirect('home')

    # Check if user is authenticated and it's the right user
    if not request.user.is_authenticated:
        messages.warning(request, 'Для прохождения теста необходимо войти в систему.')
        return redirect('login')

    if request.user != quick_app.user_created:
        messages.error(request, 'У вас нет доступа к данному тесту.')
        return redirect('home')

    # Check if user already passed the test
    if TestAttempt.objects.filter(test=test, user=request.user, passed=True).exists():
        messages.warning(request, 'Вы уже успешно прошли этот тест')
        quick_app.status = ApplicationStatus.ACCEPTED
        quick_app.save()
        messages.success(request, 'Ваша быстрая заявка была одобрена.')
        return redirect('home')

    if request.method == 'POST':
        attempt = TestAttempt.objects.create(
            test=test,
            user=request.user
        )

        score = 0
        total_points = sum(q.points for q in test.questions.all())

        for question in test.questions.all():
            answer_id = request.POST.get(f'question_{question.id}')
            if answer_id:
                selected_answer = Answer.objects.get(id=answer_id)
                UserAnswer.objects.create(
                    attempt=attempt,
                    question=question,
                    selected_answer=selected_answer
                )
                if selected_answer.is_correct:
                    score += question.points

        attempt.score = (score / total_points) * 100
        attempt.passed = attempt.score >= test.passing_score
        attempt.end_time = timezone.now()
        attempt.save()

        if attempt.passed:
            # Update quick application status
            quick_app.status = ApplicationStatus.ACCEPTED
            quick_app.save()

            # Create regular application
            regular_app = Application.objects.create(
                vacancy=quick_app.vacancy,
                user=request.user,
                cover_letter=quick_app.cover_letter,
                status=ApplicationStatus.NEW
            )

            # Calculate time spent on test
            time_spent = attempt.end_time - attempt.start_time
            minutes_spent = int(time_spent.total_seconds() // 60)
            seconds_spent = int(time_spent.total_seconds() % 60)
            time_str = f"{minutes_spent} мин {seconds_spent} сек"

            # Notify HR managers about test completion and application conversion
            hr_users = User.objects.filter(profile__role=UserRole.HR_MANAGER)
            for hr in hr_users:
                send_mail(
                    f'Быстрая заявка преобразована в обычную - Тест пройден',
                    f'''Быстрая заявка от {quick_app.full_name} на вакансию "{quick_app.vacancy.title}" была преобразована в обычную заявку.

Кандидат успешно прошел тест:
- Результат: {attempt.score:.1f}% (требовалось: {test.passing_score}%)
- Время прохождения: {time_str}
- Дата прохождения: {attempt.end_time.strftime('%d.%m.%Y в %H:%M')}

Заявка готова к дальнейшему рассмотрению.

С уважением,
Система PizzaJobs''',
                    settings.EMAIL_HOST_USER,
                    [hr.email],
                    fail_silently=False,
                )

            messages.success(request, f'Поздравляем! Вы успешно прошли тест с результатом {attempt.score:.1f}%. Ваша заявка принята и направлена на рассмотрение.')
            return redirect('home')
        else:
            quick_app.status = ApplicationStatus.REJECTED
            quick_app.save()
            messages.error(request, f'К сожалению, вы не прошли тест. Ваш результат: {attempt.score:.1f}%. Минимальный проходной балл: {test.passing_score}%')
            return redirect('home')

    return render(request, 'vacancies/take_test.html', {'test': test, 'is_quick_app': True})

def test_statistics(request):
    tests = Test.objects.all()
    total_attempts = TestAttempt.objects.count()
    passed_attempts = TestAttempt.objects.filter(passed=True).count()

    statistics = {
        'total_attempts': total_attempts,
        'passed_attempts': passed_attempts,
        'success_rate': (passed_attempts * 100 / total_attempts) if total_attempts > 0 else 0,
        'tests_data': [],
        'question_analytics': []
    }

    for test in tests:
        test_attempts = test.attempts.all()
        total = test_attempts.count()
        passed = test_attempts.filter(passed=True).count()
        avg_score = test_attempts.aggregate(Avg('score'))['score__avg'] or 0
        
        # Анализ вопросов для этого теста
        question_stats = []
        for question in test.questions.all():
            # Получаем все ответы на этот вопрос
            user_answers = UserAnswer.objects.filter(question=question)
            total_answers = user_answers.count()
            
            if total_answers > 0:
                # Считаем правильные ответы
                correct_answers = user_answers.filter(selected_answer__is_correct=True).count()
                incorrect_answers = total_answers - correct_answers
                error_rate = (incorrect_answers * 100 / total_answers) if total_answers > 0 else 0
                
                # Статистика по вариантам ответов
                answer_distribution = {}
                for answer in question.answers.all():
                    answer_count = user_answers.filter(selected_answer=answer).count()
                    answer_distribution[answer.text] = {
                        'count': answer_count,
                        'percentage': (answer_count * 100 / total_answers) if total_answers > 0 else 0,
                        'is_correct': answer.is_correct
                    }
                
                question_stats.append({
                    'question': question,
                    'total_answers': total_answers,
                    'correct_answers': correct_answers,
                    'error_rate': error_rate,
                    'difficulty_level': 'Высокая' if error_rate > 50 else 'Средняя' if error_rate > 30 else 'Низкая',
                    'answer_distribution': answer_distribution
                })
        
        statistics['tests_data'].append({
            'test': test,
            'total_attempts': total,
            'passed_attempts': passed,
            'success_rate': (passed * 100 / total) if total > 0 else 0,
            'avg_score': avg_score,
            'question_stats': question_stats
        })

    # Создаем общую статистику по всем вопросам для JavaScript
    all_questions_stats = []
    for test_data in statistics['tests_data']:
        for q_stat in test_data['question_stats']:
            all_questions_stats.append({
                'test_title': test_data['test'].position_type.title,
                'question_text': q_stat['question'].text[:50] + '...' if len(q_stat['question'].text) > 50 else q_stat['question'].text,
                'error_rate': q_stat['error_rate'],
                'total_answers': q_stat['total_answers']
            })
    
    # Сортируем по сложности
    all_questions_stats.sort(key=lambda x: x['error_rate'], reverse=True)
    statistics['question_analytics'] = all_questions_stats

    # Добавляем данные для диаграммы распределения результатов
    score_distribution = [0, 0, 0, 0, 0]  # 0-20, 21-40, 41-60, 61-80, 81-100
    all_attempts = TestAttempt.objects.filter(score__isnull=False)
    
    for attempt in all_attempts:
        score = attempt.score
        if score <= 20:
            score_distribution[0] += 1
        elif score <= 40:
            score_distribution[1] += 1
        elif score <= 60:
            score_distribution[2] += 1
        elif score <= 80:
            score_distribution[3] += 1
        else:
            score_distribution[4] += 1
    
    statistics['score_distribution'] = score_distribution

    return render(request, 'hr/test_statistics.html', {'statistics': statistics})

@login_required
@candidate_required
def candidate_tests(request):
    user = request.user

    # Получаем все заявки пользователя (обычные и быстрые)
    user_applications = Application.objects.filter(user=user)
    quick_applications = QuickApplication.objects.filter(user_created=user)

    # Собираем все типы позиций, на которые пользователь подавал заявки
    applied_position_types = set()

    # Из обычных заявок
    for app in user_applications:
        applied_position_types.add(app.vacancy.position_type)

    # Из быстрых заявок (только те, где создан аккаунт)
    for quick_app in quick_applications:
        applied_position_types.add(quick_app.vacancy.position_type)

    # Получаем тесты только для тех позиций, на которые подавались заявки
    tests = Test.objects.filter(
        is_active=True,
        position_type__in=applied_position_types
    )

    test_data = []
    for test in tests:
        # Get user's attempts for this test
        user_attempts = TestAttempt.objects.filter(test=test, user=user).order_by('-start_time')

        # Check if user has passed this test
        passed_attempt = user_attempts.filter(passed=True).first()

        # Get latest attempt
        latest_attempt = user_attempts.first()

        # Найти связанные вакансии, на которые пользователь подавал заявки
        user_related_vacancies = []

        # Из обычных заявок
        for app in user_applications:
            if app.vacancy.position_type == test.position_type:
                user_related_vacancies.append(app.vacancy)

        # Из быстрых заявок
        for quick_app in quick_applications:
            if quick_app.vacancy.position_type == test.position_type:
                user_related_vacancies.append(quick_app.vacancy)

        # Убираем дубликаты
        user_related_vacancies = list(set(user_related_vacancies))

        test_data.append({
            'test': test,
            'passed_attempt': passed_attempt,
            'latest_attempt': latest_attempt,
            'all_attempts': user_attempts,
            'related_vacancies': user_related_vacancies,
            'can_retake': not passed_attempt,  # Can retake if not passed yet
        })

    context = {
        'test_data': test_data,
        'total_tests': tests.count(),
        'passed_tests': len([td for td in test_data if td['passed_attempt']]),
        'pending_tests': len([td for td in test_data if not td['passed_attempt']]),
    }

    return render(request, 'candidates/tests.html', context)

def privacy_policy(request):
    from django.utils import timezone
    context = {
        'current_date': timezone.now()
    }
    return render(request, 'legal/privacy_policy.html', context)

@login_required
@hr_required
def manage_candidates(request):
    # Get all candidates with their application statistics
    candidates = User.objects.filter(profile__role=UserRole.CANDIDATE).select_related('profile').prefetch_related('applications__vacancy')

    # Add statistics to each candidate
    candidate_data = []
    for candidate in candidates:
        total_applications = candidate.applications.count()
        pending_applications = candidate.applications.filter(status__in=['NEW', 'REVIEWING', 'INTERVIEW_SCHEDULED']).count()
        accepted_applications = candidate.applications.filter(status='ACCEPTED').count()

        candidate_data.append({
            'candidate': candidate,
            'total_applications': total_applications,
            'pending_applications': pending_applications,
            'accepted_applications': accepted_applications,
            'latest_application': candidate.applications.order_by('-applied_at').first()
        })

    # Apply filters
    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')

    if search:
        candidate_data = [
            cd for cd in candidate_data 
            if search.lower() in f"{cd['candidate'].first_name} {cd['candidate'].last_name}".lower() or 
               search.lower() in cd['candidate'].email.lower()
        ]

    if status_filter:
        if status_filter == 'active':
            candidate_data = [cd for cd in candidate_data if cd['pending_applications'] > 0]
        elif status_filter == 'hired':
            candidate_data = [cd for cd in candidate_data if cd['accepted_applications'] > 0]
        elif status_filter == 'new':
            candidate_data = [cd for cd in candidate_data if cd['total_applications'] == 0]

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(candidate_data, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search': search,
        'status_filter': status_filter,
        'total_candidates': len(candidates),
    }
    return render(request, 'hr/manage_candidates.html', context)

@login_required
@hr_required
def create_candidate(request):
    if request.method == 'POST':
        form = HRCandidateCreationForm(request.POST)
        if form.is_valid():
            # Create user
            user = User.objects.create_user(
                username=form.cleaned_data['email'],  # Use email as username
                email=form.cleaned_data['email'],
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
                password=form.cleaned_data['password']
            )

            # Create user profile
            profile = UserProfile.objects.create(
                user=user,
                role=UserRole.CANDIDATE,
                phone=form.cleaned_data['phone'],
                city=form.cleaned_data.get('city', ''),
                about=form.cleaned_data.get('about', ''),
                desired_position=form.cleaned_data.get('desired_position', ''),
                experience=form.cleaned_data.get('experience', ''),
                education=form.cleaned_data.get('education', '')
            )

            messages.success(request, f'Кандидат {user.get_full_name()} успешно создан')
            return redirect('manage_candidates')
    else:
        form = HRCandidateCreationForm()

    context = {
        'form': form,
    }
    return render(request, 'hr/create_candidate.html', context)

@login_required
@hr_required
def view_candidate_profile(request, candidate_id):
    candidate = get_object_or_404(User, id=candidate_id, profile__role=UserRole.CANDIDATE)
    candidate_profile = candidate.profile

    # Получаем резюме кандидата
    resumes = Resume.objects.filter(user=candidate, is_active=True)

    # Получаем заявки кандидата
    applications = Application.objects.filter(user=candidate).order_by('-applied_at')

    # Получаем быстрые заявки, если есть
    quick_applications = QuickApplication.objects.filter(user_created=candidate).order_by('-created_at')

    # Получаем статистику по тестам
    test_attempts = TestAttempt.objects.filter(user=candidate).order_by('-start_time')

    context = {
        'candidate': candidate,
        'profile': candidate_profile,
        'resumes': resumes,
        'applications': applications,
        'quick_applications': quick_applications,
        'test_attempts': test_attempts,
    }
    return render(request, 'hr/candidate_profile.html', context)

@login_required
@hr_required
def apply_candidate_to_vacancy(request):
    if request.method == 'POST':
        form = ApplyCandidateForm(request.POST)
        if form.is_valid():
            candidate = form.cleaned_data['candidate']
            vacancy = form.cleaned_data['vacancy']
            cover_letter = form.cleaned_data.get('cover_letter', '')

            # Check if candidate already applied for this vacancy
            if Application.objects.filter(user=candidate, vacancy=vacancy).exists():
                messages.warning(request, f'{candidate.get_full_name()} уже подавал заявку на эту вакансию')
                return redirect('apply_candidate')

            # Create application
            application = Application.objects.create(
                user=candidate,
                vacancy=vacancy,
                cover_letter=f"[Заявка создана HR менеджером {request.user.get_full_name()}]\n\n{cover_letter}" if cover_letter else f"[Заявка создана HR менеджером {request.user.get_full_name()}]",
                status=ApplicationStatus.NEW
            )

            # Create notification for candidate
            Notification.objects.create(
                user=candidate,
                title=f'Вы были добавлены на вакансию: {vacancy.title}',
                message=f'HR менеджер {request.user.get_full_name()} подал заявку от вашего имени на вакансию "{vacancy.title}". Вы можете отслеживать статус в личном кабинете.'
            )

            messages.success(request, f'Заявка от {candidate.get_full_name()} на вакансию "{vacancy.title}" успешно создана')
            return redirect('application_detail', application_id=application.id)
    else:
        form = ApplyCandidateForm()

    context = {
        'form': form,
    }
    return render(request, 'hr/apply_candidate.html', context)