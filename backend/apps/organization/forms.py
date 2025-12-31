"""
用户注册表单
"""
import re
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from .models import Lawyer


class LawyerRegistrationForm(UserCreationForm):
    """律师注册表单"""
    
    class Meta:
        model = Lawyer
        fields = ('username', 'password1', 'password2')
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 设置字段样式
        self.fields['username'].widget.attrs.update({
            'class': 'form-input',
            'placeholder': '请输入中文姓名'
        })
        self.fields['password1'].widget.attrs.update({
            'class': 'form-input',
            'placeholder': '请输入密码'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-input',
            'placeholder': '请确认密码'
        })
        
        # 更新标签
        self.fields['username'].label = "用户名/真实姓名"
        self.fields['password1'].label = "密码"
        self.fields['password2'].label = "确认密码"
        
        # 清除帮助文本
        self.fields['username'].help_text = '只能输入中文'
        self.fields['password1'].help_text = ''
        self.fields['password2'].help_text = ''
    
    def _is_first_user(self) -> bool:
        """检查是否为第一个注册的用户"""
        return not Lawyer.objects.exists()
    
    def clean_username(self):
        """验证用户名必须是中文"""
        username = self.cleaned_data.get('username')
        if username:
            # 检查是否全部为中文字符
            if not re.match(r'^[\u4e00-\u9fa5]+$', username):
                raise ValidationError('用户名只能输入中文')
        return username
    
    def save(self, commit=True):
        """保存用户，根据是否为第一个用户设置权限"""
        user = super().save(commit=False)
        # 将用户名同时保存到 real_name 字段
        user.real_name = user.username
        
        # 第一个注册的用户拥有所有权限（管理员）
        # 后续用户需要管理员开通权限
        if self._is_first_user():
            user.is_staff = True
            user.is_superuser = True
            user.is_admin = True
        else:
            user.is_staff = False
            user.is_superuser = False
            user.is_admin = False
            user.is_active = True  # 账号激活，但无后台权限
        
        if commit:
            user.save()
        return user
