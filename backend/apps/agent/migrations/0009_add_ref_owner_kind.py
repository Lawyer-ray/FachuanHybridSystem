"""AgentAttachment 加 ref_owner_kind：引用型附件区分合同/案件绑定文件夹。

存量引用全部指向合同，default='contract' 即存量语义；ref_contract_id
字段名保留（避免连锁改名），语义泛化为「归属 id」。
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("agent", "0008_agentapprovalpolicy")]

    operations = [
        migrations.AddField(
            model_name="agentattachment",
            name="ref_owner_kind",
            field=models.CharField(
                blank=True,
                choices=[("contract", "合同"), ("case", "案件")],
                default="contract",
                max_length=16,
                verbose_name="引用归属类型",
            ),
        ),
    ]
