from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import Q
from .models import ConviteUsuario, User, UserRole
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


def gerar_username_unico(email, nome):
    base = email.split('@')[0] if email and '@' in email else nome.lower().replace(' ', '')
    base = "".join(c for c in base if c.isalnum() or c in ['_', '.'])
    if not base:
        base = "usuario"
    username = base
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f"{base}{counter}"
        counter += 1
    return username


@login_required
def usuarios_list_view(request):
    """
    Listagem de usuários do sistema (exceto superusuários) e cadastro de novos usuários
    com senha padrão Seami@2026.
    """
    pode_cadastrar = request.user.is_superuser or request.user.role in [UserRole.MASTER_ADMIN, UserRole.DIRETOR]

    if request.method == 'POST':
        if not pode_cadastrar:
            messages.error(request, "Você não tem permissão para cadastrar novos usuários.")
            return redirect('accounts:usuarios_list')

        nome = request.POST.get('nome', '').strip()
        email = request.POST.get('email', '').strip().lower()
        role = request.POST.get('role', '').strip()
        telefone = request.POST.get('telefone', '').strip()

        valid_roles = [UserRole.PROFESSOR, UserRole.COORDENADOR, UserRole.DIRETOR, UserRole.AUXILIAR]

        if not nome:
            messages.error(request, "Por favor, informe o nome do usuário.")
        elif not email:
            messages.error(request, "Por favor, informe o e-mail do usuário.")
        elif role not in valid_roles:
            messages.error(request, "Selecione um perfil de acesso válido.")
        elif User.objects.filter(email__iexact=email).exists():
            messages.error(request, f"Já existe um usuário com o e-mail '{email}'.")
        else:
            try:
                username = gerar_username_unico(email, nome)
                novo_usuario = User.objects.create_user(
                    username=username,
                    email=email,
                    password="Seami@2026",
                    first_name=nome,
                    role=role,
                    telefone=telefone,
                    is_active=True
                )
                messages.success(
                    request,
                    f"Usuário '{nome}' cadastrado com sucesso! A senha inicial padrão é 'Seami@2026'."
                )
                return redirect('accounts:usuarios_list')
            except Exception as e:
                messages.error(request, f"Erro ao cadastrar usuário: {str(e)}")

    # Filtros de busca
    q = request.GET.get('q', '').strip()
    role_filter = request.GET.get('role', '').strip()

    usuarios = User.objects.filter(is_superuser=False)

    if q:
        usuarios = usuarios.filter(
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(username__icontains=q) |
            Q(email__icontains=q)
        )

    if role_filter:
        usuarios = usuarios.filter(role=role_filter)

    usuarios = usuarios.order_by('-is_active', 'first_name', 'username')

    roles_disponiveis = [
        (UserRole.PROFESSOR, 'Professor(a)'),
        (UserRole.COORDENADOR, 'Coordenador(a)'),
        (UserRole.DIRETOR, 'Diretor(a)'),
        (UserRole.AUXILIAR, 'Auxiliar'),
    ]

    return render(request, 'accounts/usuarios_list.html', {
        'usuarios': usuarios,
        'pode_cadastrar': pode_cadastrar,
        'roles_disponiveis': roles_disponiveis,
        'busca_q': q,
        'role_selecionada': role_filter,
        'active_tab': 'usuarios',
    })


@login_required
def usuario_editar_view(request, user_id):
    """
    Edição dos dados de um usuário pelo Diretor ou Master Admin/Superuser.
    """
    pode_gerenciar = request.user.is_superuser or request.user.role in [UserRole.MASTER_ADMIN, UserRole.DIRETOR]
    if not pode_gerenciar:
        messages.error(request, "Você não tem permissão para editar usuários.")
        return redirect('accounts:usuarios_list')

    usuario = get_object_or_404(User, id=user_id)
    if usuario.is_superuser and not request.user.is_superuser:
        messages.error(request, "Apenas superusuários podem editar contas de administradores master.")
        return redirect('accounts:usuarios_list')

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        email = request.POST.get('email', '').strip().lower()
        role = request.POST.get('role', '').strip()
        telefone = request.POST.get('telefone', '').strip()
        is_active = request.POST.get('is_active') == '1'
        nova_senha = request.POST.get('nova_senha', '').strip()

        valid_roles = [UserRole.PROFESSOR, UserRole.COORDENADOR, UserRole.DIRETOR, UserRole.AUXILIAR]

        if not nome:
            messages.error(request, "O nome não pode ficar em branco.")
        elif not email:
            messages.error(request, "O e-mail não pode ficar em branco.")
        elif role not in valid_roles:
            messages.error(request, "Selecione um perfil de acesso válido.")
        elif User.objects.filter(email__iexact=email).exclude(id=usuario.id).exists():
            messages.error(request, f"Já existe outro usuário com o e-mail '{email}'.")
        else:
            try:
                usuario.first_name = nome
                usuario.email = email
                usuario.role = role
                usuario.telefone = telefone
                usuario.is_active = is_active
                if nova_senha:
                    usuario.set_password(nova_senha)
                usuario.save()
                messages.success(request, f"Usuário '{nome}' atualizado com sucesso!")
            except Exception as e:
                messages.error(request, f"Erro ao atualizar usuário: {str(e)}")

    return redirect('accounts:usuarios_list')


@login_required
def usuario_excluir_view(request, user_id):
    """
    Exclusão de um usuário pelo Diretor ou Master Admin/Superuser.
    """
    pode_gerenciar = request.user.is_superuser or request.user.role in [UserRole.MASTER_ADMIN, UserRole.DIRETOR]
    if not pode_gerenciar:
        messages.error(request, "Você não tem permissão para excluir usuários.")
        return redirect('accounts:usuarios_list')

    usuario = get_object_or_404(User, id=user_id)

    if usuario.id == request.user.id:
        messages.error(request, "Você não pode excluir sua própria conta.")
        return redirect('accounts:usuarios_list')

    if usuario.is_superuser:
        messages.error(request, "Não é permitido excluir contas de administradores master por aqui.")
        return redirect('accounts:usuarios_list')

    if request.method == 'POST':
        nome = usuario.get_full_name() or usuario.username
        try:
            usuario.delete()
            messages.success(request, f"Usuário '{nome}' foi excluído com sucesso.")
        except Exception as e:
            messages.error(request, f"Erro ao excluir usuário: {str(e)}")

    return redirect('accounts:usuarios_list')


@login_required
def alterar_senha_view(request):
    """
    Página de alteração de senha disponível para todos os usuários autenticados.
    """
    if request.method == 'POST':
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            # Mantém a sessão ativa após a troca de senha
            update_session_auth_hash(request, user)
            messages.success(request, "Sua senha foi alterada com sucesso!")
            return redirect('accounts:alterar_senha')
        else:
            messages.error(request, "Por favor, corrija os erros abaixo.")
    else:
        form = PasswordChangeForm(user=request.user)

    return render(request, 'accounts/alterar_senha.html', {
        'form': form,
        'active_tab': 'alterar_senha',
    })

