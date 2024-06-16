from django.urls import path
from kms_app import views
from django.shortcuts import redirect

urlpatterns = [
    # URL Default ke Home
    path('', lambda request: redirect('home/', permanent=False)),
    
    path('home/', views.home, name='home'), 
    path('articles/', views.articles, name='articles'), 
    path('articles/<int:document_id>/', views.detail_article, name='detailArticle'), 
    path('document/<int:document_id>/', views.detail_article, name='detailArticle'), 
    path('search/', views.home, name='search'),
    path('uploadKnowledge/', views.add_knowledge, name='addKnowledge'),
    path('uploaders/uploadKnowledge/', views.upload_knowledge, name='uploadKnowledge'),
    path('login/', views.login, name="login"),
    path('logout/', views.logout, name="logout"),
]
