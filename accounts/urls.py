from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(template_name='accounts/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('primeiro-acesso/', views.primeiro_acesso_view, name='primeiro_acesso'),
    path('usuarios/', views.usuarios_list_view, name='usuarios_list'),
    path('usuarios/<int:user_id>/editar/', views.usuario_editar_view, name='usuario_editar'),
    path('usuarios/<int:user_id>/excluir/', views.usuario_excluir_view, name='usuario_excluir'),
    path('alterar-senha/', views.alterar_senha_view, name='alterar_senha'),
]
