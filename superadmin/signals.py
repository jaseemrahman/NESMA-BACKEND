from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from superadmin.context_processors import clear_sidebar_counts
from superadmin.models import Blog, BlogCategory, CareerApplication, Enquiry
from website.cache import bump_api_cache_version


@receiver([post_save, post_delete], sender=Blog)
@receiver([post_save, post_delete], sender=BlogCategory)
def invalidate_blog_api_cache(sender, **kwargs):
    bump_api_cache_version()


@receiver([post_save, post_delete], sender=Enquiry)
@receiver([post_save, post_delete], sender=CareerApplication)
def invalidate_sidebar_counts(sender, **kwargs):
    clear_sidebar_counts()


@receiver(pre_save, sender=Blog)
def delete_replaced_blog_image(sender, instance, **kwargs):
    """Remove the old image file from storage (after commit) when a blog's image is replaced."""
    update_fields = kwargs.get('update_fields')
    if not instance.pk or (update_fields is not None and 'image' not in update_fields):
        return
    old_name = Blog.objects.filter(pk=instance.pk).values_list('image', flat=True).first()
    if old_name and old_name != instance.image.name:
        storage = instance.image.storage
        transaction.on_commit(lambda: storage.delete(old_name))


@receiver(post_delete, sender=Blog)
def delete_blog_image_file(sender, instance, **kwargs):
    if instance.image:
        instance.image.delete(save=False)
