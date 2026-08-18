import logging
from django.core.mail import send_mail
from django.conf import settings
from .models import ConviteUsuario, User

logger = logging.getLogger(__name__)

def gerar_e_enviar_convite(nome: str, email: str, role: str, request_host: str) -> ConviteUsuario:
    """
    Cria ou atualiza o convite com um token UUID e envia o Link Mágico por e-mail.
    """
    convite, _ = ConviteUsuario.objects.update_or_create(
        email=email,
        defaults={'nome': nome, 'role': role, 'utilizado': False}
    )

    link_magico = f"{request_host.rstrip('/')}/accounts/primeiro-acesso/?token={convite.token}"

    assunto = "Bem-vindo(a) ao SEAMI - Definição de Senha e Primeiro Acesso"
    mensagem = (
        f"Olá, {nome}!\n\n"
        f"Você foi convidado(a) para acessar o sistema SEAMI como {convite.get_role_display()}.\n"
        f"Para definir sua senha pessoal e ativar sua conta, acesse o link seguro abaixo:\n\n"
        f"{link_magico}\n\n"
        f"Este link é válido por 48 horas.\n"
        f"Se você não esperava este convite, por favor desconsidere."
    )

    try:
        send_mail(
            subject=assunto,
            message=mensagem,
            from_email=settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'noreply@seami.local',
            recipient_list=[email],
            fail_silently=False
        )
    except Exception as exc:
        logger.warning(f"Não foi possível enviar o e-mail de convite para {email}: {exc}")

    return convite


def ativar_usuario_por_token(token: str, password: str) -> User:
    """
    Valida o token do convite e cria o usuário com a senha escolhida.
    """
    convite = ConviteUsuario.objects.filter(token=token).first()
    if not convite or not convite.is_valido:
        raise ValueError("O link de convite é inválido, expirou ou já foi utilizado.")

    # Se já existir usuário com esse email, apenas ativa e define senha
    usuario = User.objects.filter(email=convite.email).first()
    if not usuario:
        username = convite.email.split('@')[0]
        # Garante username único se já houver outro
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        usuario = User.objects.create_user(
            username=username,
            email=convite.email,
            first_name=convite.nome,
            role=convite.role,
            password=password,
            is_active=True
        )
    else:
        usuario.set_password(password)
        usuario.role = convite.role
        usuario.is_active = True
        usuario.save()

    convite.utilizado = True
    convite.save(update_fields=['utilizado'])
    return usuario
