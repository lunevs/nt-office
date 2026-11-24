from django.db import migrations, models


def to_verification(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    # Аккаунты, созданные до этого изменения, считаем подтверждёнными.
    User.objects.filter(pending=False).update(verified=True)
    # Висящие заявки на доступ превращаются в обычные неподтверждённые аккаунты со входом.
    User.objects.filter(pending=True).update(is_active=True, verified=False)


def back(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(verified=False, is_active=True, is_superuser=False).update(pending=True, is_active=False)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_telegram_and_access_requests")]

    operations = [
        migrations.AddField(model_name="user", name="verified", field=models.BooleanField(default=False, verbose_name="Аккаунт подтверждён")),
        migrations.AddField(model_name="user", name="verification_requested_at", field=models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="Запрошено подтверждение")),
        migrations.RunPython(to_verification, back),
        migrations.RemoveField(model_name="user", name="pending"),
    ]
