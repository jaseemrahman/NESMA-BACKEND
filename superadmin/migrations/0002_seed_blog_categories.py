from django.db import migrations

CATEGORIES = [
    ('News', 'أخبار', 'news'),
    ('Article', 'مقالات', 'article'),
    ('Announcement', 'إعلانات', 'announcement'),
    ('Insights', 'رؤى', 'insights'),
]


def seed(apps, schema_editor):
    BlogCategory = apps.get_model('superadmin', 'BlogCategory')
    for index, (name, name_ar, slug) in enumerate(CATEGORIES, start=1):
        BlogCategory.objects.get_or_create(slug=slug, defaults={'name': name, 'name_ar': name_ar, 'sequence': index})


def unseed(apps, schema_editor):
    BlogCategory = apps.get_model('superadmin', 'BlogCategory')
    BlogCategory.objects.filter(slug__in=[c[2] for c in CATEGORIES], blogs__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('superadmin', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
