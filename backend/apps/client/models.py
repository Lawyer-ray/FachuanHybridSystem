from django.db import models
from django.core.exceptions import ValidationError


class Client(models.Model):
    NATURAL = "natural"
    LEGAL = "legal"
    NON_LEGAL_ORG = "non_legal_org"
    CLIENT_TYPE_CHOICES = [
        (NATURAL, "自然人"),
        (LEGAL, "法人"),
        (NON_LEGAL_ORG, "非法人组织"),
    ]

    name = models.CharField(max_length=255, verbose_name="名称")
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="联系电话")
    address = models.CharField(max_length=255, blank=True, null=True, default="", verbose_name="住所地")
    client_type = models.CharField(max_length=16, choices=CLIENT_TYPE_CHOICES, default=LEGAL, verbose_name="主体类型")
    id_number = models.CharField(max_length=64, blank=True, null=True, verbose_name="身份证号码或统一社会信用代码")
    legal_representative = models.CharField(max_length=255, blank=True, null=True, verbose_name="法定代表人或负责人")
    is_our_client = models.BooleanField(default=False, verbose_name="是否为我方当事人")

    def __str__(self) -> str:
        return self.name

    def clean(self):
        if self.client_type == self.LEGAL and not self.legal_representative:
            raise ValidationError({"legal_representative": "Required for legal organizations"})

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "当事人"
        verbose_name_plural = "当事人"
        db_table = "cases_client"
        managed = True


def client_identity_doc_upload_path(instance, filename):
    """生成当事人证件文件上传路径"""
    import os
    from django.utils.text import slugify
    
    # 获取文件扩展名
    _, ext = os.path.splitext(filename)
    
    # 清理当事人名称
    client_name = instance.client.name if instance.client else "未知"
    client_name = slugify(client_name) or "unknown"
    
    # 获取证件类型显示名称
    doc_type_display = dict(ClientIdentityDoc.DOC_TYPE_CHOICES).get(instance.doc_type, instance.doc_type)
    doc_type_display = slugify(doc_type_display) or instance.doc_type
    
    # 生成文件名：当事人名称_证件类型.扩展名
    new_filename = f"{client_name}_{doc_type_display}{ext}"
    
    return f"client_identity_docs/{new_filename}"


class ClientIdentityDoc(models.Model):
    ID_CARD = "id_card"
    PASSPORT = "passport"
    HK_MACAO_PERMIT = "hk_macao_permit"
    RESIDENCE_PERMIT = "residence_permit"
    HOUSEHOLD_REGISTER = "household_register"
    BUSINESS_LICENSE = "business_license"
    LEGAL_REP_CERT = "legal_rep_certificate"
    LEGAL_REP_ID_CARD = "legal_rep_id_card"
    DOC_TYPE_CHOICES = [
        (ID_CARD, "身份证"),
        (PASSPORT, "护照"),
        (HK_MACAO_PERMIT, "港澳通行证"),
        (RESIDENCE_PERMIT, "居住证"),
        (HOUSEHOLD_REGISTER, "户口本"),
        (BUSINESS_LICENSE, "营业执照"),
        (LEGAL_REP_CERT, "法定代表人身份证明书"),
        (LEGAL_REP_ID_CARD, "法定代表人身份证"),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="identity_docs", verbose_name="当事人")
    doc_type = models.CharField(max_length=32, choices=DOC_TYPE_CHOICES, verbose_name="证件类型")
    file_path = models.CharField(max_length=512, verbose_name="文件路径")
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="上传时间")

    def __str__(self) -> str:
        return f"{self.client.name}-{self.doc_type}"

    def media_url(self) -> str | None:
        from django.conf import settings
        import os
        if not self.file_path:
            return None
        try:
            root = str(settings.MEDIA_ROOT)
            # 如果是绝对路径，转换为相对路径
            if self.file_path.startswith(root):
                rel = os.path.relpath(self.file_path, root)
                return settings.MEDIA_URL + rel.replace(os.sep, "/")
            # 如果已经是相对路径，直接拼接
            elif not os.path.isabs(self.file_path):
                return settings.MEDIA_URL + self.file_path.replace(os.sep, "/")
        except Exception:
            return None
        return None

    def clean(self):
        if self.client:
            natural_docs = {self.ID_CARD, self.PASSPORT, self.HK_MACAO_PERMIT, self.RESIDENCE_PERMIT, self.HOUSEHOLD_REGISTER}
            legal_docs = {self.BUSINESS_LICENSE, self.LEGAL_REP_CERT, self.LEGAL_REP_ID_CARD}
            if self.client.client_type == Client.NATURAL and self.doc_type not in natural_docs:
                raise ValidationError({"doc_type": "Invalid doc type for natural person"})
            if self.client.client_type in {Client.LEGAL, Client.NON_LEGAL_ORG} and self.doc_type not in natural_docs | legal_docs:
                raise ValidationError({"doc_type": "Invalid doc type for organization"})

    class Meta:
        verbose_name = "当事人证件文件"
        verbose_name_plural = "当事人证件文件"
        db_table = "cases_clientidentitydoc"
        managed = False


class PropertyClue(models.Model):
    """财产线索模型"""
    BANK = "bank"
    ALIPAY = "alipay"
    WECHAT = "wechat"
    REAL_ESTATE = "real_estate"
    OTHER = "other"
    
    CLUE_TYPE_CHOICES = [
        (BANK, "银行"),
        (ALIPAY, "支付宝账户"),
        (WECHAT, "微信账户"),
        (REAL_ESTATE, "不动产"),
        (OTHER, "其他"),
    ]
    
    CONTENT_TEMPLATES = {
        BANK: "户名：\n开户行：\n银行账号：",
        WECHAT: "微信号：\n微信实名：",
        ALIPAY: "支付宝账号：\n支付宝实名：",
        REAL_ESTATE: "",
        OTHER: "",
    }
    
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="property_clues",
        verbose_name="当事人"
    )
    clue_type = models.CharField(
        max_length=16,
        choices=CLUE_TYPE_CHOICES,
        default=BANK,
        verbose_name="线索类型"
    )
    content = models.TextField(
        blank=True,
        default="",
        verbose_name="线索内容"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")
    
    def __str__(self) -> str:
        return f"{self.client.name}-{self.get_clue_type_display()}"
    
    class Meta:
        verbose_name = "财产线索"
        verbose_name_plural = "财产线索"
        db_table = "cases_propertyclue"
        managed = True


class PropertyClueAttachment(models.Model):
    """财产线索附件模型"""
    property_clue = models.ForeignKey(
        PropertyClue,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name="财产线索"
    )
    file_path = models.CharField(max_length=512, verbose_name="文件路径")
    file_name = models.CharField(max_length=255, verbose_name="文件名")
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="上传时间")
    
    def __str__(self) -> str:
        return f"{self.property_clue}-{self.file_name}"
    
    def media_url(self) -> str | None:
        """返回附件的媒体 URL"""
        from django.conf import settings
        import os
        if not self.file_path:
            return None
        try:
            root = str(settings.MEDIA_ROOT)
            if self.file_path.startswith(root):
                rel = os.path.relpath(self.file_path, root)
                return settings.MEDIA_URL + rel.replace(os.sep, "/")
        except Exception:
            return None
        return None
    
    class Meta:
        verbose_name = "财产线索附件"
        verbose_name_plural = "财产线索附件"
        db_table = "cases_propertyclueattachment"
        managed = True