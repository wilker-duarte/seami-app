from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, ConviteUsuario


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Controle de Acesso SEAMI', {'fields': ('role', 'telefone')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Controle de Acesso SEAMI', {'fields': ('role', 'telefone')}),
    )
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active')
    search_fields = ('username', 'first_name', 'last_name', 'email')


@admin.register(ConviteUsuario)
class ConviteUsuarioAdmin(admin.ModelAdmin):
    list_display = ('nome', 'email', 'role', 'token', 'expira_em', 'utilizado', 'criado_em')
    list_filter = ('role', 'utilizado')
    search_fields = ('nome', 'email', 'token')
    readonly_fields = ('token', 'criado_em')
