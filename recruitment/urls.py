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
path('vacancies/<int:vacancy_id>/quick-apply/', views.quick_apply, name='quick_apply'),
    path('applications/', views.application_list, name='application_list'),
    path('applications/<int:application_id>/', views.application_detail, name='application_detail'),
    path('comments/<int:comment_id>/delete/', views.delete_comment, name='delete_comment'),
    path('comments/<int:comment_id>/moderate/', views.moderate_comment, name='moderate_comment'),

    # HR dashboard routes
    path('hr/dashboard/', views.hr_dashboard, name='hr_dashboard'),
    path('hr/vacancies/', views.manage_vacancies, name='manage_vacancies'),
    path('hr/vacancies/create/', views.create_vacancy, name='create_vacancy'),
    path('hr/vacancies/edit/<int:vacancy_id>/', views.edit_vacancy, name='edit_vacancy'),
    path('hr/vacancies/toggle/<int:vacancy_id>/', views.toggle_vacancy_status, name='toggle_vacancy_status'),

    # Restaurant manager dashboard routes
    path('manager/dashboard/', views.manager_dashboard, name='manager_dashboard'),
    path('manager/vacancies/create/', views.create_vacancy_manager, name='create_vacancy_manager'),

    # Notification routes
    path('notifications/', views.notifications, name='notifications'),
    path('hr/quick-applications/', views.quick_applications, name='quick_applications'),
    path('hr/quick-applications/<int:app_id>/convert/', views.convert_quick_application, name='convert_quick_application'),
    path('hr/quick-applications/<int:app_id>/update-status/', views.update_quick_application_status, name='update_quick_application_status'),
    path('hr/quick-applications/<int:app_id>/delete/', views.delete_quick_application, name='delete_quick_application'),

    # Test management URLs
    path('hr/tests/', views.manage_tests, name='manage_tests'),
    path('hr/tests/select-position/', views.select_position_for_test, name='select_position_for_test'),
    path('hr/position-types/<int:position_type_id>/create-test/', views.create_test, name='create_test'),
    path('hr/tests/create-all/', views.create_tests_for_all_vacancies, name='create_tests_for_all_vacancies'),
    path('hr/tests/<int:test_id>/edit/', views.edit_test, name='edit_test'),
    path('hr/tests/<int:test_id>/delete/', views.delete_test, name='delete_test'),
    path('hr/tests/<int:test_id>/toggle/', views.toggle_test, name='toggle_test'),
    path('hr/test-statistics/', views.test_statistics, name='test_statistics'),
    path('test/<int:test_id>/take/', views.take_test, name='take_test'),
    path('test/token/<str:token>/', views.take_test_by_token, name='take_test_by_token'),
    path('candidate/tests/', views.candidate_tests, name='candidate_tests'),

    # Legal URLs
    path('privacy-policy/', views.privacy_policy, name='privacy_policy'),

    # Candidate Management URLs
    path('hr/candidates/', views.manage_candidates, name='manage_candidates'),
    path('hr/candidates/create/', views.create_candidate, name='create_candidate'),
    path('hr/candidates/apply/', views.apply_candidate_to_vacancy, name='apply_candidate'),
]