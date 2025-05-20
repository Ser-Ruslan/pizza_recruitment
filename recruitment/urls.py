from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('profile/', views.view_profile, name='view_profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/upload-resume/', views.upload_resume, name='upload_resume'),
    path('profile/delete-resume/<int:resume_id>/', views.delete_resume, name='delete_resume'),
    path('vacancies/', views.vacancy_list, name='vacancy_list'),
    path('vacancy/<int:vacancy_id>/', views.vacancy_detail, name='vacancy_detail'),
    path('vacancy/<int:vacancy_id>/apply/', views.apply_for_vacancy, name='apply_for_vacancy'),
    path('applications/', views.application_list, name='application_list'),
    path('application/<int:application_id>/', views.application_detail, name='application_detail'),
    path('hr/dashboard/', views.hr_dashboard, name='hr_dashboard'),
    path('manager/dashboard/', views.manager_dashboard, name='manager_dashboard'),
    path('notifications/', views.notifications, name='notifications'),
    path('logout/', views.logout_view, name='logout'),
]

urlpatterns = [
    # Home page
    path('', views.home, name='home'),
    
    # Authentication
    path('register/', views.register, name='register'),
    
    # Profile routes
    path('profile/', views.view_profile, name='view_profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/upload-resume/', views.upload_resume, name='upload_resume'),
    path('profile/delete-resume/<int:resume_id>/', views.delete_resume, name='delete_resume'),
    
    # Vacancy routes
    path('vacancies/', views.vacancy_list, name='vacancy_list'),
    path('vacancies/<int:vacancy_id>/', views.vacancy_detail, name='vacancy_detail'),
    
    # Application routes
    path('vacancies/<int:vacancy_id>/apply/', views.apply_for_vacancy, name='apply_for_vacancy'),
    path('applications/', views.application_list, name='application_list'),
    path('applications/<int:application_id>/', views.application_detail, name='application_detail'),
    
    # HR dashboard routes
    path('hr/dashboard/', views.hr_dashboard, name='hr_dashboard'),
    path('hr/vacancies/', views.manage_vacancies, name='manage_vacancies'),
    path('hr/vacancies/create/', views.create_vacancy, name='create_vacancy'),
    path('hr/vacancies/edit/<int:vacancy_id>/', views.edit_vacancy, name='edit_vacancy'),
    path('hr/vacancies/toggle/<int:vacancy_id>/', views.toggle_vacancy_status, name='toggle_vacancy_status'),
    
    # Restaurant manager dashboard routes
    path('manager/dashboard/', views.manager_dashboard, name='manager_dashboard'),
    
    # Notification routes
    path('notifications/', views.notifications, name='notifications'),
]
