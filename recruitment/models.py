from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
import os

# Constants for user roles
class UserRole(models.TextChoices):
    CANDIDATE = 'CANDIDATE', 'Кандидат'
    HR_MANAGER = 'HR_MANAGER', 'HR Менеджер'
    RESTAURANT_MANAGER = 'RESTAURANT_MANAGER', 'Менеджер пицерий'
    ADMIN = 'ADMIN', 'Администратор'

# Constants for application status
class ApplicationStatus(models.TextChoices):
    NEW = 'NEW', 'Новая'
    REVIEWING = 'REVIEWING', 'На рассмотрении'
    INTERVIEW_SCHEDULED = 'INTERVIEW_SCHEDULED', 'Запланированное собеседование'
    REJECTED = 'REJECTED', 'Отклонено'
    ACCEPTED = 'ACCEPTED', 'Принято'
    ON_HOLD = 'ON_HOLD', 'На паузе'

# User Profile Model
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.CANDIDATE)
    phone = models.CharField(max_length=15, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)
    about = models.TextField(blank=True, null=True)
    
    # Additional fields for candidates
    desired_position = models.CharField(max_length=100, blank=True, null=True)
    experience = models.TextField(blank=True, null=True)
    education = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

# Function to handle resume file paths
def resume_file_path(instance, filename):
    # Get the file extension
    ext = filename.split('.')[-1]
    # Format the filename
    filename = f"resume_{instance.user.username}_{timezone.now().strftime('%Y%m%d%H%M%S')}.{ext}"
    # Return the full path
    return os.path.join('resumes', filename)

# Candidate Resume Model
class Resume(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='resumes')
    file = models.FileField(upload_to=resume_file_path)
    title = models.CharField(max_length=100)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.title} - {self.user.username}"
    
    def clean(self):
        # Validate file type and size
        if self.file:
            file_name = self.file.name.lower()
            allowed_extensions = ['.pdf', '.doc', '.docx']
            if not any(file_name.endswith(ext) for ext in allowed_extensions):
                raise ValueError("Only PDF and Word documents are allowed.")
            if self.file.size > settings.MAX_RESUME_SIZE:
                raise ValueError("File size cannot exceed 5MB.")
        
        super().clean()

# Restaurant Model
class Restaurant(models.Model):
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_restaurants')
    
    def __str__(self):
        return f"{self.name} - {self.city}"

# Position Type Model
class PositionType(models.Model):
    title = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    
    def __str__(self):
        return self.title

# Vacancy Model
class Vacancy(models.Model):
    title = models.CharField(max_length=100)
    position_type = models.ForeignKey(PositionType, on_delete=models.CASCADE, related_name='vacancies')
    restaurants = models.ManyToManyField(Restaurant, related_name='vacancies')
    description = models.TextField()
    requirements = models.TextField()
    responsibilities = models.TextField()
    conditions = models.TextField()
    salary_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    salary_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_vacancies')
    
    def __str__(self):
        return f"{self.title} - {self.position_type.title}"
    
    class Meta:
        verbose_name_plural = "Vacancies"

# Application Model
class Application(models.Model):
    vacancy = models.ForeignKey(Vacancy, on_delete=models.CASCADE, related_name='applications')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='applications')
    resume = models.ForeignKey(Resume, on_delete=models.SET_NULL, null=True, blank=True, related_name='applications')
    cover_letter = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=ApplicationStatus.choices, default=ApplicationStatus.NEW)
    applied_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} application for {self.vacancy.title}"

# Interview Model
class Interview(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='interviews')
    scheduled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='scheduled_interviews')
    interviewer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='assigned_interviews')
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='interviews')
    date_time = models.DateTimeField()
    location = models.CharField(max_length=255)
    is_online = models.BooleanField(default=False)
    meeting_link = models.URLField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    completed = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Interview for {self.application.user.username} on {self.date_time}"

# Application Comment Model
class ApplicationComment(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='application_comments')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Comment by {self.author.username} on {self.application.user.username}'s application"

# Notification Model
class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=100)
    message = models.TextField()
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Notification for {self.user.username}: {self.title}"
