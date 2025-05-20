from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from .models import (
    UserProfile, Resume, Vacancy, Application, 
    Interview, ApplicationComment, UserRole
)

# User registration form
class UserRegisterForm(UserCreationForm):
    email = forms.EmailField(label=_('Email'), required=True)
    first_name = forms.CharField(label=_('Имя'), required=True)
    last_name = forms.CharField(label=_('Фамилия'), required=True)
    
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password1', 'password2']
        labels = {
            'username': _('Логин'),
            'password1': _('Пароль'),
            'password2': _('Подтверждение пароля'),
        }
        
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        
        if commit:
            user.save()
            
        return user

# User profile form
class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['phone', 'city', 'photo', 'about', 'desired_position', 'experience', 'education']
        widgets = {
            'about': forms.Textarea(attrs={'rows': 4}),
            'experience': forms.Textarea(attrs={'rows': 4}),
            'education': forms.Textarea(attrs={'rows': 4}),
        }
        labels = {
            'phone': _('Телефон'),
            'city': _('Город'),
            'photo': _('Фотография'),
            'about': _('О себе'),
            'desired_position': _('Желаемая должность'),
            'experience': _('Опыт работы'),
            'education': _('Образование'),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make fields not required for non-candidates
        if self.instance and self.instance.role != UserRole.CANDIDATE:
            self.fields['desired_position'].required = False
            self.fields['experience'].required = False
            self.fields['education'].required = False

# Resume upload form
class ResumeUploadForm(forms.ModelForm):
    class Meta:
        model = Resume
        fields = ['title', 'file']
        labels = {
            'title': _('Название'),
            'file': _('Файл резюме'),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['file'].validators.append(
            FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx'])
        )
        
    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            # Check file size
            if file.size > settings.MAX_RESUME_SIZE:
                raise forms.ValidationError("Размер файла не может превышать 5МБ.")
            
            # Check file type
            content_type = file.content_type
            if content_type not in settings.ALLOWED_RESUME_TYPES:
                raise forms.ValidationError("Разрешены только PDF и Word документы.")
        
        return file

# Vacancy form
class VacancyForm(forms.ModelForm):
    class Meta:
        model = Vacancy
        fields = [
            'title', 'position_type', 'restaurants', 
            'description', 'requirements', 'responsibilities', 
            'conditions', 'salary_min', 'salary_max', 'is_active'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'requirements': forms.Textarea(attrs={'rows': 4}),
            'responsibilities': forms.Textarea(attrs={'rows': 4}),
            'conditions': forms.Textarea(attrs={'rows': 4}),
        }
        labels = {
            'title': _('Название'),
            'position_type': _('Тип должности'),
            'restaurants': _('Рестораны'),
            'description': _('Описание'),
            'requirements': _('Требования'),
            'responsibilities': _('Обязанности'),
            'conditions': _('Условия'),
            'salary_min': _('Минимальная зарплата'),
            'salary_max': _('Максимальная зарплата'),
            'is_active': _('Активна'),
        }

# Application form
class ApplicationForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ['resume', 'cover_letter']
        widgets = {
            'cover_letter': forms.Textarea(attrs={'rows': 4}),
        }
        labels = {
            'resume': _('Резюме'),
            'cover_letter': _('Сопроводительное письмо'),
        }
        
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user:
            # Only show active resumes for the current user
            self.fields['resume'].queryset = Resume.objects.filter(
                user=user, is_active=True
            )

# Application status form
class ApplicationStatusForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ['status']
        labels = {
            'status': _('Статус'),
        }

# Application comment form
class ApplicationCommentForm(forms.ModelForm):
    class Meta:
        model = ApplicationComment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'content': _('Комментарий'),
        }

# Interview form
class InterviewForm(forms.ModelForm):
    class Meta:
        model = Interview
        fields = ['interviewer', 'restaurant', 'date_time', 'location', 'is_online', 'meeting_link', 'notes']
        widgets = {
            'date_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'interviewer': _('Интервьюер'),
            'restaurant': _('Ресторан'),
            'date_time': _('Дата и время'),
            'location': _('Место проведения'),
            'is_online': _('Онлайн интервью'),
            'meeting_link': _('Ссылка на встречу'),
            'notes': _('Примечания'),
        }
        
    def __init__(self, *args, **kwargs):
        application = kwargs.pop('application', None)
        super().__init__(*args, **kwargs)
        
        if application:
            # Only show restaurants related to the vacancy
            self.fields['restaurant'].queryset = application.vacancy.restaurants.all()
            
            # Only show restaurant managers or HR managers as interviewers
            self.fields['interviewer'].queryset = User.objects.filter(
                profile__role__in=[UserRole.HR_MANAGER, UserRole.RESTAURANT_MANAGER]
            )
