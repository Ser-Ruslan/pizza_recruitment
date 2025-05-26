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
    TestAttempt, Question, Answer, UserAnswer
)
from .forms import (
    UserRegisterForm, UserProfileForm, ResumeUploadForm, 
    VacancyForm, ApplicationForm, ApplicationStatusForm, 
    InterviewForm, ApplicationCommentForm, QuickApplicationForm
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
    comments = ApplicationComment.objects.filter(application=application).order_by('created_at')
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

        # Process comment form submission
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

                # Update application status
                old_status = application.status
                application.status = ApplicationStatus.INTERVIEW_SCHEDULED
                application.save()

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
@login_required
@hr_required
def hr_dashboard(request):
    # Get statistics
    total_vacancies = Vacancy.objects.count()
    active_vacancies = Vacancy.objects.filter(is_active=True).count()
    total_applications = Application.objects.count()
    new_regular_applications = Application.objects.filter(status=ApplicationStatus.NEW).count()
    new_quick_applications = QuickApplication.objects.filter(status=ApplicationStatus.NEW).count()
    new_applications = new_regular_applications + new_quick_applications
    interviews_scheduled = Interview.objects.filter(
        date_time__gte=timezone.now()
    ).count()

    # Recent applications
    recent_applications = Application.objects.order_by('-applied_at')[:10]

    # Vacancies by status
    vacancies_by_status = Vacancy.objects.values('is_active').annotate(
        count=Count('id')
    )

    # Applications by status
    applications_by_status = Application.objects.values('status').annotate(
        count=Count('id')
    )

    # Test statistics
    total_test_attempts = TestAttempt.objects.count()
    passed_test_attempts = TestAttempt.objects.filter(passed=True).count()
    test_success_rate = (passed_test_attempts * 100 / total_test_attempts) if total_test_attempts > 0 else 0
    
    # Statistics by competency (position type)
    competency_stats = []
    # Get all active tests
    all_tests = Test.objects.filter(is_active=True)
    
    for test in all_tests:
        test_attempts = test.attempts.all()
        total = test_attempts.count()
        passed = test_attempts.filter(passed=True).count()
        avg_score = test_attempts.aggregate(Avg('score'))['score__avg'] or 0
        
        competency_stats.append({
            'position_type': test.position_type.title,
            'total_attempts': total,
            'passed_attempts': passed,
            'success_rate': (passed * 100 / total) if total > 0 else 0,
            'avg_score': avg_score
        })

    test_statistics = {
        'total_attempts': total_test_attempts,
        'passed_attempts': passed_test_attempts,
        'success_rate': test_success_rate,
        'competency_stats': competency_stats
    }

    context = {
        'total_vacancies': total_vacancies,
        'active_vacancies': active_vacancies,
        'total_applications': total_applications,
        'new_applications': new_applications,
        'new_regular_applications': new_regular_applications,
        'new_quick_applications': new_quick_applications,
        'interviews_scheduled': interviews_scheduled,
        'recent_applications': recent_applications,
        'vacancies_by_status': vacancies_by_status,
        'applications_by_status': applications_by_status,
        'test_statistics': test_statistics,
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
    vacancies = Vacancy.objects.filter(test__isnull=True)
    
    for vacancy in vacancies:
        # Создаем базовый тест для каждой вакансии
        test = Test.objects.create(
            vacancy=vacancy,
            title=f"Тест для вакансии {vacancy.title}",
            description=f"Тестирование знаний и навыков для позиции {vacancy.title}",
            time_limit=30,
            passing_score=70
        )
        
        # Создаем базовые вопросы для теста
        questions = [
            {
                "text": f"Опишите ваш опыт работы, связанный с позицией {vacancy.title}",
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
    
    messages.success(request, 'Тесты успешно созданы для всех вакансий без тестов')
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
        'tests_data': []
    }

    for test in tests:
        test_attempts = test.attempts.all()
        total = test_attempts.count()
        passed = test_attempts.filter(passed=True).count()
        statistics['tests_data'].append({
            'test': test,
            'total_attempts': total,
            'passed_attempts': passed,
            'success_rate': (passed * 100 / total) if total > 0 else 0,
            'avg_score': test_attempts.aggregate(Avg('score'))['score__avg'] or 0
        })

    return render(request, 'hr/test_statistics.html', {'statistics': statistics})

@login_required
@candidate_required
def candidate_tests(request):
    user = request.user
    
    # Get all active tests
    tests = Test.objects.filter(is_active=True)
    
    test_data = []
    for test in tests:
        # Get user's attempts for this test
        user_attempts = TestAttempt.objects.filter(test=test, user=user).order_by('-start_time')
        
        # Check if user has passed this test
        passed_attempt = user_attempts.filter(passed=True).first()
        
        # Get latest attempt
        latest_attempt = user_attempts.first()
        
        # Find related vacancies for this position type
        related_vacancies = Vacancy.objects.filter(
            position_type=test.position_type, 
            is_active=True
        )
        
        test_data.append({
            'test': test,
            'passed_attempt': passed_attempt,
            'latest_attempt': latest_attempt,
            'all_attempts': user_attempts,
            'related_vacancies': related_vacancies,
            'can_retake': not passed_attempt,  # Can retake if not passed yet
        })
    
    context = {
        'test_data': test_data,
        'total_tests': tests.count(),
        'passed_tests': len([td for td in test_data if td['passed_attempt']]),
        'pending_tests': len([td for td in test_data if not td['passed_attempt']]),
    }
    
    return render(request, 'candidates/tests.html', context)