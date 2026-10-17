import io
import os
import uuid

from django.core.files.base import ContentFile
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from PIL import Image, ImageOps


LANGUAGE_CHOICES = (('en', 'English'), ('ar', 'Arabic'))


def validate_image(file):
    """Return True when `file` is a real image Pillow can read (rejects renamed non-image files)."""
    try:
        Image.open(file).verify()
        return True
    except Exception:
        return False
    finally:
        file.seek(0)


def optimize_image(file):
    """
    Lossless / visually-lossless size optimisation that never changes resolution or format:
      - JPEG: re-saved with the ORIGINAL quantisation tables (quality='keep') + optimised
              Huffman tables + progressive encoding; ICC profile and EXIF are preserved.
      - PNG:  lossless re-compression.
      - Other formats (WebP, GIF, ...) are left untouched.
    Returns a ContentFile only when the result is smaller than the upload, otherwise None.
    """
    try:
        file.seek(0)
        original = file.read()
        file.seek(0)
        img = Image.open(io.BytesIO(original))
        fmt = img.format
        buffer = io.BytesIO()
        if fmt == 'JPEG':
            params = {'quality': 'keep', 'subsampling': 'keep', 'optimize': True, 'progressive': True}
            for key in ('icc_profile', 'exif'):
                if img.info.get(key):
                    params[key] = img.info[key]
            img.save(buffer, format='JPEG', **params)
        elif fmt == 'PNG':
            params = {'optimize': True}
            if img.info.get('icc_profile'):
                params['icc_profile'] = img.info['icc_profile']
            img.save(buffer, format='PNG', **params)
        else:
            return None
        if buffer.tell() >= len(original):
            return None
        return ContentFile(buffer.getvalue(), name=os.path.basename(file.name))
    except Exception:
        return None


THUMBNAIL_SIZE = (160, 160)


def make_thumbnail(image_file):
    """
    Small JPEG preview (max 160px) for admin lists only - the original upload is never modified.
    Returns a ContentFile, or None if the file can't be read as an image.
    """
    try:
        image_file.seek(0)
        img = Image.open(image_file)
        img.draft('RGB', (THUMBNAIL_SIZE[0] * 2, THUMBNAIL_SIZE[1] * 2))  # fast JPEG decode at reduced size
        img = ImageOps.exif_transpose(img).convert('RGB')
        img.thumbnail(THUMBNAIL_SIZE, Image.LANCZOS)
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=85, optimize=True)
        image_file.seek(0)
        name = os.path.splitext(os.path.basename(image_file.name))[0]
        return ContentFile(buffer.getvalue(), name=f'{name}_thumb.jpg')
    except Exception:
        return None


class BaseModel(models.Model):
    """
    Abstract base model with common fields.
    """
    is_active = models.BooleanField(default=True)
    sequence = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BlogCategory(BaseModel):
    """
    Media centre categories (News, Article, Announcement, Insights ...).
    """
    name = models.CharField(max_length=150)
    name_ar = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True, editable=False)  # auto from English name

    class Meta:
        verbose_name = 'Blog Category'
        verbose_name_plural = 'Blog Categories'
        ordering = ['sequence', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:170]
        super().save(*args, **kwargs)


class Blog(BaseModel):
    """
    Media centre post (news / article / announcement).
    Mandatory: title, category, image, content, date
    """
    # db_index=False: covered by the (category, is_active) composite index below
    category = models.ForeignKey(BlogCategory, on_delete=models.PROTECT, related_name='blogs', db_index=False)
    title = models.CharField(max_length=255)
    title_ar = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True, editable=False)  # auto from English title
    location = models.CharField(max_length=150, blank=True, default='')
    location_ar = models.CharField(max_length=150, blank=True, default='')
    date = models.DateField(default=timezone.localdate)
    image = models.ImageField(upload_to='blogs/')
    # small preview for admin lists (generated automatically from `image`)
    thumbnail = models.ImageField(upload_to='blogs/thumbs/', blank=True, editable=False)
    short_description = models.TextField(blank=True, default='')
    short_description_ar = models.TextField(blank=True, default='')
    content = models.TextField()
    content_ar = models.TextField()
    meta_title = models.CharField(max_length=255, blank=True, default='')
    meta_description = models.CharField(max_length=500, blank=True, default='')

    class Meta:
        verbose_name = 'Blog'
        verbose_name_plural = 'Blogs'
        ordering = ['sequence', '-date', '-id']
        indexes = [
            models.Index(fields=['is_active', 'sequence', '-date'], name='blog_active_order_idx'),
            models.Index(fields=['category', 'is_active'], name='blog_category_active_idx'),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:255]
        # Optimise only freshly uploaded images (not files already in storage)
        if self.image and not getattr(self.image, '_committed', True):
            thumb = make_thumbnail(self.image)
            if thumb:
                self.thumbnail.save(thumb.name, thumb, save=False)
            optimized = optimize_image(self.image)
            if optimized:
                self.image.save(optimized.name, optimized, save=False)
        super().save(*args, **kwargs)


class Enquiry(models.Model):
    """
    Website enquiries from the footer form and the contact page form.
    Footer: full name (stored in first_name), email, message
    Contact page: first name, last name, company, phone, email, message
    """
    SOURCE_FOOTER = 'footer'
    SOURCE_CONTACT = 'contact'
    SOURCE_CHOICES = ((SOURCE_FOOTER, 'Footer Form'), (SOURCE_CONTACT, 'Contact Page'))

    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_CONTACT)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150, blank=True, default='')
    company_name = models.CharField(max_length=200, blank=True, default='')
    phone = models.CharField(max_length=30, blank=True, default='')
    email = models.EmailField()
    message = models.TextField(blank=True, default='')
    language = models.CharField(max_length=2, choices=LANGUAGE_CHOICES, default='en')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Enquiry'
        verbose_name_plural = 'Enquiries'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['source', '-created_at'], name='enquiry_source_created_idx'),
        ]

    def __str__(self):
        return f'{self.full_name} <{self.email}>'

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()


def cv_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f'careers/cv/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{ext}'


class CareerApplication(models.Model):
    """
    General job applications submitted from the careers page.
    """
    EDUCATION_CHOICES = (
        ('High School', 'High School'),
        ('Diploma', 'Diploma'),
        ("Bachelor's Degree", "Bachelor's Degree"),
        ("Master's Degree", "Master's Degree"),
        ('PhD', 'PhD'),
    )
    STATUS_NEW = 'new'
    STATUS_CHOICES = (
        (STATUS_NEW, 'New'),
        ('reviewed', 'Reviewed'),
        ('shortlisted', 'Shortlisted'),
        ('rejected', 'Rejected'),
        ('hired', 'Hired'),
    )
    CV_EXTENSIONS = ['pdf', 'doc', 'docx']

    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150, blank=True, default='')
    email = models.EmailField()
    mobile = models.CharField(max_length=30)
    current_location = models.CharField(max_length=200)
    nationality = models.CharField(max_length=100, blank=True, default='')
    education = models.CharField(max_length=50, choices=EDUCATION_CHOICES)
    degree = models.CharField(max_length=200)
    cv = models.FileField(upload_to=cv_upload_path, validators=[FileExtensionValidator(CV_EXTENSIONS)])
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
    admin_notes = models.TextField(blank=True, default='')
    language = models.CharField(max_length=2, choices=LANGUAGE_CHOICES, default='en')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Career Application'
        verbose_name_plural = 'Career Applications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at'], name='career_status_created_idx'),
        ]

    def __str__(self):
        return f'{self.full_name} - {self.degree}'

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    @property
    def cv_filename(self):
        return os.path.basename(self.cv.name) if self.cv else ''
