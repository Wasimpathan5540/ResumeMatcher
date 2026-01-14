from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('roles/', views.role_suggestion, name='role_suggestion'),
    path('job-check/', views.job_check, name='job_check'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('history/<int:pk>/', views.history_detail, name='history_detail'),
    path('history/<int:pk>/pdf/', views.history_pdf, name='history_pdf'),
   
   
]
