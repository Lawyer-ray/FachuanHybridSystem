"""
用户注册视图
"""
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login
from .forms import LawyerRegistrationForm


def register(request):
    """用户注册视图"""
    if request.method == 'POST':
        form = LawyerRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # 注册成功后自动登录
            login(request, user)
            messages.success(request, f'注册成功！欢迎 {user.real_name or user.username}')
            return redirect('admin:index')
    else:
        form = LawyerRegistrationForm()
    
    return render(request, 'admin/register.html', {
        'form': form,
        'title': '用户注册',
    })
