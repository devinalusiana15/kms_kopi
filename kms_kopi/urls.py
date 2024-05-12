from django.urls import path
from kms_app import views
from django.shortcuts import redirect

urlpatterns = [
    # URL Default ke Home
    path('', lambda request: redirect('home/', permanent=False)),
    
    path('home/', views.home, name='home'), 
    path('articles/', views.articles, name='articles'), 
    path('search/', views.home, name='search'),
    path('uploadKnowledge/', views.upload_file, name='upload_file'),
]
