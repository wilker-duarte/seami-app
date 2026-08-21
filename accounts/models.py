from django.contrib.auth.models import AbstractUser, UserManager as BaseUserManager
# pyrefly: ignore [missing-import]
from django.db import models
# pyrefly: ignore [missing-import]
from django.utils import timezone
from datetime import timedelta
import uuid

class UserRole(models.TextChoices):
    MASTER_ADMIN = 'MASTER_ADMIN', 'Master Admin'
    DIRETOR = 'DIRETOR', 'Diretor(a)'
    COORDENADOR = 'COORDENADOR', 'Coordenador(a)'
    ENFERMEIRA = 'ENFERMEIRA', 'Enfermeira'
    PROFESSOR = 'PROFESSOR', 'Professor(a)'
    AUXILIAR = 'AUXILIAR', 'Auxiliar'

class UserManager(BaseUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', UserRole.MASTER_ADMIN)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser precisa ter is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser precisa ter is_superuser=True.')

        return self._create_user(username, email, password, **extra_fields)

class User(AbstractUser):
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.PROFESSOR,
        verbose_name='Perfil de Acesso'
    )
    telefone = models.CharField(
        max_length=20, 
        blank=True, 
        null=True,
        verbose_name='Telefone'
    )

    objects = UserManager()

    class Meta:
        verbose_name = 'Usuário'
        verbose_name_plural = 'Usuários'

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    def save(self, *args, **kwargs):
        # Se for superuser, garante que o papel seja MASTER_ADMIN e is_staff=True
        if self.is_superuser:
            self.role = UserRole.MASTER_ADMIN
            self.is_staff = True
        super().save(*args, **kwargs)

    @property
    def is_master_admin(self):
        return self.role == UserRole.MASTER_ADMIN or self.is_superuser

    @property
    def is_diretor(self):
        return self.role in [UserRole.DIRETOR, UserRole.MASTER_ADMIN] or self.is_superuser

    @property
    def is_coordenador(self):
        return self.role == UserRole.COORDENADOR

    @property
    def is_enfermeira(self):
        return self.role == UserRole.ENFERMEIRA or self.role in [UserRole.DIRETOR, UserRole.MASTER_ADMIN] or self.is_superuser

    @property
    def is_professor(self):
        return self.role == UserRole.PROFESSOR

    @property
    def is_auxiliar(self):
        return self.role == UserRole.AUXILIAR


class ConviteUsuario(models.Model):
    """
    Token temporário e seguro para Link Mágico de Primeiro Acesso.
    Permite ao administrador convidar educadores sem necessidade de senha manual inicial.
    """

    email = models.EmailField(unique=True, verbose_name='E-mail do Convidado')
    nome = models.CharField(max_length=150, verbose_name='Nome Completo')
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.PROFESSOR,
        verbose_name='Perfil Concedido'
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='Token de Acesso')
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    expira_em = models.DateTimeField(verbose_name='Expira em')
    utilizado = models.BooleanField(default=False, verbose_name='Já Utilizado')

    class Meta:
        verbose_name = 'Convite de Usuário'
        verbose_name_plural = 'Convites de Usuários'
        ordering = ['-criado_em']

    def __str__(self):
        return f"Convite: {self.email} ({self.get_role_display()}) - {'Utilizado' if self.utilizado else 'Pendente'}"

    def save(self, *args, **kwargs):

        if not self.expira_em:
            self.expira_em = timezone.now() + timedelta(days=2)  # 48 horas de validade padrão
        super().save(*args, **kwargs)

    @property
    def is_valido(self):
        return not self.utilizado and timezone.now() <= self.expira_em
