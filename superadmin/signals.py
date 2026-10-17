from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from superadmin.models import Blog, BlogCategory
from website.cache import bump_api_cache_version


@receiver([post_save, post_delete], sender=Blog)
@receiver([post_save, post_delete], sender=BlogCategory)
def invalidate_blog_api_cache(sender, **kwargs):
    bump_api_cache_version()


@receiver(pre_save, sender=Blog)
def delete_replaced_blog_image(sender, instance, **kwargs):
    """Remove the old image + thumbnail files from storage (after commit) when a blog's image is replaced."""
    update_fields = kwargs.get('update_fields')
    if not instance.pk or (update_fields is not None and 'image' not in update_fields):
        return
    old = Blog.objects.filter(pk=instance.pk).values_list('image', 'thumbnail').first()
    if not old:
        return
    old_image, old_thumb = old
    storage = instance.image.storage
    stale = [name for name, current in ((old_image, instance.image.name), (old_thumb, instance.thumbnail.name))
             if name and name != current]
    if stale:
        transaction.on_commit(lambda: [storage.delete(name) for name in stale])


@receiver(post_delete, sender=Blog)
def delete_blog_image_file(sender, instance, **kwargs):
    for field in (instance.image, instance.thumbnail):
        if field:
            field.delete(save=False)
