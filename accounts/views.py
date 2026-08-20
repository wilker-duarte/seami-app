from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from .models import ConviteUsuario
from .services import ativar_usuario_por_token, gerar_e_enviar_convite


def logout_view(request):
    """
    Encerra a sessão do usuário e redireciona de volta para a tela de login oficial do SEAMI.
    """
    logout(request)
    return redirect('accounts:login')


def primeiro_acesso_view(request):
    """
    Tela de ativação de conta e definição de senha através do Link Mágico.
    """
    token = request.GET.get('token') or request.POST.get('token')
    if not token:
        messages.error(request, "Token de convite não fornecido.")
        return render(request, 'accounts/primeiro_acesso.html', {'invalido': True})

    convite = ConviteUsuario.objects.filter(token=token).first()
    if not convite or not convite.is_valido:
        messages.error(request, "Este link de convite é inválido, expirou ou já foi utilizado.")
        return render(request, 'accounts/primeiro_acesso.html', {'invalido': True})

    if request.method == 'POST':
        password = request.POST.get('password', '').strip()
        password_confirm = request.POST.get('password_confirm', '').strip()

        if len(password) < 8:
            messages.error(request, "A senha deve ter no mínimo 8 caracteres.")
        elif password != password_confirm:
            messages.error(request, "As senhas não coincidem.")
        else:
            try:
                usuario = ativar_usuario_por_token(token, password)
                login(request, usuario)
                messages.success(request, f"Bem-vindo(a), {usuario.first_name}! Sua conta foi ativada com sucesso.")
                return redirect('core:dashboard')
            except Exception as e:
                messages.error(request, str(e))

    return render(request, 'accounts/primeiro_acesso.html', {
        'convite': convite,
        'token': token,
        'invalido': False
    })
