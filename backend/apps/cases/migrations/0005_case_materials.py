from django.db import migrations, models
import django.db.models.deletion


def seed_case_material_types(apps, schema_editor) -> None:
    CaseMaterialType = apps.get_model("cases", "CaseMaterialType")

    party_defaults = [
        "起诉状",
        "答辩状",
        "反诉状",
        "反诉答辩状",
        "上诉状",
        "强制执行申请书",
        "律师调查令申请书",
        "其他材料",
    ]
    non_party_defaults = [
        "受理通知书",
        "组成人员通知书",
        "传票",
        "出庭通知书",
        "民事裁定书",
        "民事判决书",
    ]

    for name in party_defaults:
        CaseMaterialType.objects.get_or_create(
            law_firm_id=None,
            category="party",
            name=name,
            defaults={"is_active": True},
        )

    for name in non_party_defaults:
        CaseMaterialType.objects.get_or_create(
            law_firm_id=None,
            category="non_party",
            name=name,
            defaults={"is_active": True},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("organization", "0003_alter_lawyer_license_pdf"),
        ("cases", "0004_remove_caselog_reminder_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="CaseMaterialType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.CharField(choices=[("party", "当事人材料"), ("non_party", "非当事人材料")], max_length=32, verbose_name="材料大类")),
                ("name", models.CharField(max_length=64, verbose_name="类型名称")),
                ("is_active", models.BooleanField(default=True, verbose_name="是否启用")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                (
                    "law_firm",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="case_material_types", to="organization.lawfirm", verbose_name="律所"),
                ),
            ],
            options={
                "verbose_name": "案件材料类型",
                "verbose_name_plural": "案件材料类型",
            },
        ),
        migrations.CreateModel(
            name="CaseMaterial",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.CharField(choices=[("party", "当事人材料"), ("non_party", "非当事人材料")], max_length=32, verbose_name="材料大类")),
                ("type_name", models.CharField(max_length=64, verbose_name="类型名称")),
                ("side", models.CharField(blank=True, choices=[("our", "我方当事人材料"), ("opponent", "对方当事人材料")], max_length=32, null=True, verbose_name="当事人方向")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("case", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="materials", to="cases.case", verbose_name="案件")),
                (
                    "source_attachment",
                    models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="bound_material", to="cases.caselogattachment", verbose_name="来源日志附件"),
                ),
                (
                    "supervising_authority",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="materials", to="cases.supervisingauthority", verbose_name="主管机关"),
                ),
                (
                    "type",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="materials", to="cases.casematerialtype", verbose_name="材料类型"),
                ),
            ],
            options={
                "verbose_name": "案件材料",
                "verbose_name_plural": "案件材料",
            },
        ),
        migrations.CreateModel(
            name="CaseMaterialGroupOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.CharField(choices=[("party", "当事人材料"), ("non_party", "非当事人材料")], max_length=32, verbose_name="材料大类")),
                ("side", models.CharField(blank=True, choices=[("our", "我方当事人材料"), ("opponent", "对方当事人材料")], max_length=32, null=True, verbose_name="当事人方向")),
                ("sort_index", models.PositiveIntegerField(default=0, verbose_name="排序")),
                ("case", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="material_group_orders", to="cases.case", verbose_name="案件")),
                (
                    "supervising_authority",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="material_group_orders", to="cases.supervisingauthority", verbose_name="主管机关"),
                ),
                (
                    "type",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="group_orders", to="cases.casematerialtype", verbose_name="材料类型"),
                ),
            ],
            options={
                "verbose_name": "案件材料分组顺序",
                "verbose_name_plural": "案件材料分组顺序",
            },
        ),
        migrations.AddField(
            model_name="casematerial",
            name="parties",
            field=models.ManyToManyField(blank=True, related_name="materials", to="cases.caseparty", verbose_name="关联当事人"),
        ),
        migrations.AddConstraint(
            model_name="casematerialtype",
            constraint=models.UniqueConstraint(fields=("law_firm", "category", "name"), name="uniq_case_material_type_scope"),
        ),
        migrations.AddIndex(
            model_name="casematerialtype",
            index=models.Index(fields=["category", "name"], name="cases_casem_category_0b8b1b_idx"),
        ),
        migrations.AddIndex(
            model_name="casematerialtype",
            index=models.Index(fields=["law_firm", "category"], name="cases_casem_law_fi_4c32e8_idx"),
        ),
        migrations.AddIndex(
            model_name="casematerialtype",
            index=models.Index(fields=["is_active"], name="cases_casem_is_acti_1c4e3b_idx"),
        ),
        migrations.AddIndex(
            model_name="casematerial",
            index=models.Index(fields=["case", "category", "created_at"], name="cases_casem_case_id_168df1_idx"),
        ),
        migrations.AddIndex(
            model_name="casematerial",
            index=models.Index(fields=["case", "category", "side"], name="cases_casem_case_id_d806df_idx"),
        ),
        migrations.AddIndex(
            model_name="casematerial",
            index=models.Index(fields=["case", "category", "supervising_authority"], name="cases_casem_case_id_a9d1b0_idx"),
        ),
        migrations.AddIndex(
            model_name="casematerial",
            index=models.Index(fields=["type_name"], name="cases_casem_type_na_2374de_idx"),
        ),
        migrations.AddConstraint(
            model_name="casematerialgrouporder",
            constraint=models.UniqueConstraint(fields=("case", "category", "side", "supervising_authority", "type"), name="uniq_case_material_group_order"),
        ),
        migrations.AddIndex(
            model_name="casematerialgrouporder",
            index=models.Index(fields=["case", "category", "side", "sort_index"], name="cases_casem_case_id_7d945d_idx"),
        ),
        migrations.AddIndex(
            model_name="casematerialgrouporder",
            index=models.Index(fields=["case", "category", "supervising_authority", "sort_index"], name="cases_casem_case_id_7c1963_idx"),
        ),
        migrations.RunPython(seed_case_material_types, reverse_code=migrations.RunPython.noop),
    ]
