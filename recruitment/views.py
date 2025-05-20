from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate, logout
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Q, F, Case, When, Value, FloatField
from django.db.models.functions import Round
from .models import Vacancy, ApplicationStatus
from django.http import HttpResponseForbidden, JsonResponse
from django.core.paginator import Paginator
from django.utils import timezone
from django.urls import reverse

from .models import (
    User, UserProfile, Resume, Restaurant, PositionType, 
    Vacancy, Application, Interview, ApplicationComment, 
    Notification, UserRole, ApplicationStatus
)
from .forms import (
    UserRegisterForm, UserProfileForm, ResumeUploadForm, 
    VacancyForm, ApplicationForm, ApplicationStatusForm, 
    InterviewForm, ApplicationCommentForm
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
    
    # Get recent vacancies
    recent_vacancies = Vacancy.objects.filter(is_active=True).order_by('-created_at')[:3]
    
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
    
    # Check if user has already applied
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
    
    context = {
        'vacancy': vacancy,
        'user_applied': user_applied,
        'total_applications': total_applications,
        'acceptance_rate':     acceptance_rate,
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
            application = form.save(commit=False)
            application.vacancy = vacancy
            application.user = request.user
            application.save()
            
            # Create notification for restaurant managers
            for restaurant in vacancy.restaurants.all():
                if restaurant.manager:
                    Notification.objects.create(
                        user=restaurant.manager,
                        title=f"Новая заявка на {vacancy.title}",
                        message=f"Поступила новая заявка от {request.user.get_full_name()} на вакансии {vacancy.title}."
                    )
            
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
    
    elif user_profile.role == UserRole.HR_MANAGER:
        # HR managers see all applications
        applications = Application.objects.all().order_by('-applied_at')
    
    elif user_profile.role == UserRole.RESTAURANT_MANAGER:
        # Restaurant managers see applications for their restaurant's vacancies
        managed_restaurants = Restaurant.objects.filter(manager=request.user)
        applications = Application.objects.filter(
            vacancy__restaurants__in=managed_restaurants
        ).distinct().order_by('-applied_at')
    
    else:
        # Admin sees all applications
        applications = Application.objects.all().order_by('-applied_at')
    
    # Apply filters
    status_filter = request.GET.get('status', '')
    if status_filter:
        applications = applications.filter(status=status_filter)
    
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
    
    context = {
        'page_obj': page_obj,
        'statuses': ApplicationStatus.choices,
        'vacancies': vacancies,
        'selected_status': status_filter,
        'selected_vacancy': vacancy_filter,
    }
    return render(request, 'applications/list.html', context)

@login_required
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
                
                # Create notifications
                Notification.objects.create(
                    user=application.user,
                    title="Собеседование назначено",
                    message=f"Для вашей заявки на {application.vacancy.title} назначено собеседование {interview.date_time.strftime('%d.%m.%Y в %H:%M')}."
                )
                
                if interview.interviewer:
                    Notification.objects.create(
                        user=interview.interviewer,
                        title="Вас назначили интервьюером",
                        message=f"Вас назначили проводить собеседование с {application.user.get_full_name()} по вакансии {application.vacancy.title} {interview.date_time.strftime('%d.%m.%Y в %H:%M')}."
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
@login_required
@hr_required
def hr_dashboard(request):
    # Get statistics
    total_vacancies = Vacancy.objects.count()
    active_vacancies = Vacancy.objects.filter(is_active=True).count()
    total_applications = Application.objects.count()
    new_applications = Application.objects.filter(status=ApplicationStatus.NEW).count()
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
    
    context = {
        'total_vacancies': total_vacancies,
        'active_vacancies': active_vacancies,
        'total_applications': total_applications,
        'new_applications': new_applications,
        'interviews_scheduled': interviews_scheduled,
        'recent_applications': recent_applications,
        'vacancies_by_status': vacancies_by_status,
        'applications_by_status': applications_by_status,
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
def logout_view(request):
    if request.method == 'POST':
        logout(request)
        messages.success(request, 'Вы успешно вышли из системы')
        return redirect('home')
    return render(request, 'registration/logout.html')
