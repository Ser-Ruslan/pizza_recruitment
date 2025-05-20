from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import (
    UserProfile, Resume, Restaurant, PositionType, 
    Vacancy, Application, Interview, ApplicationComment, 
    Notification
)

# Inline admin for UserProfile in User admin
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'

# Extend the User admin
class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'get_role', 'is_staff')
    
    def get_role(self, obj):
        try:
            return obj.profile.get_role_display()
        except UserProfile.DoesNotExist:
            return None
    
    get_role.short_description = 'Role'

# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

# Resume admin
@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'uploaded_at', 'is_active')
    list_filter = ('is_active', 'uploaded_at')
    search_fields = ('title', 'user__username', 'user__email')

# Restaurant admin
@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'address', 'manager')
    list_filter = ('city',)
    search_fields = ('name', 'city', 'address')
    raw_id_fields = ('manager',)

# Position Type admin
@admin.register(PositionType)
class PositionTypeAdmin(admin.ModelAdmin):
    list_display = ('title',)
    search_fields = ('title', 'description')

# Vacancy admin
@admin.register(Vacancy)
class VacancyAdmin(admin.ModelAdmin):
    list_display = ('title', 'position_type', 'is_active', 'created_at', 'created_by')
    list_filter = ('is_active', 'position_type', 'created_at')
    search_fields = ('title', 'description', 'requirements')
    filter_horizontal = ('restaurants',)
    raw_id_fields = ('created_by',)
    
    fieldsets = (
        (None, {
            'fields': ('title', 'position_type', 'is_active')
        }),
        ('Details', {
            'fields': ('description', 'requirements', 'responsibilities', 'conditions')
        }),
        ('Salary', {
            'fields': ('salary_min', 'salary_max')
        }),
        ('Relationships', {
            'fields': ('restaurants', 'created_by')
        }),
    )

# Application admin
@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ('user', 'vacancy', 'status', 'applied_at', 'updated_at')
    list_filter = ('status', 'applied_at')
    search_fields = ('user__username', 'user__email', 'vacancy__title')
    raw_id_fields = ('user', 'vacancy', 'resume')

# Interview admin
@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ('application', 'date_time', 'interviewer', 'restaurant', 'is_online', 'completed')
    list_filter = ('date_time', 'is_online', 'completed')
    search_fields = ('application__user__username', 'application__vacancy__title')
    raw_id_fields = ('application', 'scheduled_by', 'interviewer', 'restaurant')

# Application Comment admin
@admin.register(ApplicationComment)
class ApplicationCommentAdmin(admin.ModelAdmin):
    list_display = ('application', 'author', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('application__user__username', 'author__username', 'content')
    raw_id_fields = ('application', 'author')

# Notification admin
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'read', 'created_at')
    list_filter = ('read', 'created_at')
    search_fields = ('user__username', 'title', 'message')
    raw_id_fields = ('user',)
