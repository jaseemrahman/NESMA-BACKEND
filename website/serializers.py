import re

from django.conf import settings
from rest_framework import serializers

from superadmin.helper import absolute_media_url, media_base_url
from superadmin.models import Blog, BlogCategory, CareerApplication, Enquiry

PHONE_REGEX = re.compile(r'^\+?[0-9\s\-().]{7,20}$')
# src/href pointing at local media inside rich-text content: "/media/..." or "http(s)://<any host>/media/..."
CONTENT_MEDIA_REGEX = re.compile(r'(src|href)=(["\'])(?:https?://[^/"\']+)?(' + re.escape(settings.MEDIA_URL) + r')')

MESSAGES = {
    'required': {'en': 'This field is required.', 'ar': 'هذا الحقل مطلوب.'},
    'phone_invalid': {'en': 'Enter a valid phone number.', 'ar': 'يرجى إدخال رقم هاتف صحيح.'},
    'cv_size': {'en': 'CV file size must be under {size} MB.', 'ar': 'يجب أن يكون حجم السيرة الذاتية أقل من {size} ميجابايت.'},
    'cv_type': {'en': 'Only PDF, DOC or DOCX files are allowed.', 'ar': 'يُسمح فقط بملفات PDF أو DOC أو DOCX.'},
    'cv_invalid': {'en': 'The uploaded CV file is not a valid document.', 'ar': 'ملف السيرة الذاتية المرفوع غير صالح.'},
}


def translate(key, lang='en', **kwargs):
    return MESSAGES[key].get(lang, MESSAGES[key]['en']).format(**kwargs)


AR_MONTHS = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
             'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']


class AbsoluteMediaField(serializers.Field):
    """Read-only image/file field rendered as a full https URL (independent of the request host)."""
    def __init__(self, **kwargs):
        kwargs['read_only'] = True
        super().__init__(**kwargs)

    def to_representation(self, value):
        return absolute_media_url(value) or None


def absolutize_content_media(html):
    """Rewrite media links inside blog HTML to full https URLs."""
    if not html:
        return html
    base = media_base_url()
    return CONTENT_MEDIA_REGEX.sub(lambda m: f'{m.group(1)}={m.group(2)}{base}{m.group(3)}', html)


class LocalizedSerializerMixin:
    """
    Returns `<field>_ar` values when the request language is Arabic,
    falling back to the English value when the Arabic one is empty.
    """
    def lang(self):
        return self.context.get('lang', 'en')

    def localized(self, obj, field):
        if self.lang() == 'ar':
            value = getattr(obj, f'{field}_ar', '')
            if value:
                return value
        return getattr(obj, field, '')


# ── CONTENT (READ) ──────────────────────────────────────────────────────────
class BlogCategorySerializer(LocalizedSerializerMixin, serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = BlogCategory
        fields = ['id', 'name', 'slug']

    def get_name(self, obj):
        return self.localized(obj, 'name')


class BlogListSerializer(LocalizedSerializerMixin, serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    short_description = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    formatted_date = serializers.SerializerMethodField()
    image = AbsoluteMediaField()

    class Meta:
        model = Blog
        fields = ['id', 'slug', 'title', 'category', 'location', 'date', 'formatted_date', 'image', 'short_description']

    def get_title(self, obj):
        return self.localized(obj, 'title')

    def get_location(self, obj):
        return self.localized(obj, 'location')

    def get_short_description(self, obj):
        return self.localized(obj, 'short_description')

    def get_category(self, obj):
        category = obj.category
        return {'id': category.id, 'name': self.localized(category, 'name'), 'slug': category.slug}

    def get_formatted_date(self, obj):
        if self.lang() == 'ar':
            return f'{obj.date.day} {AR_MONTHS[obj.date.month - 1]} {obj.date.year}'
        return obj.date.strftime('%b %d, %Y').upper()


class BlogDetailSerializer(BlogListSerializer):
    content = serializers.SerializerMethodField()
    meta_title = serializers.SerializerMethodField()
    meta_description = serializers.SerializerMethodField()

    class Meta(BlogListSerializer.Meta):
        fields = BlogListSerializer.Meta.fields + ['content', 'meta_title', 'meta_description', 'updated_at']

    def get_content(self, obj):
        return absolutize_content_media(self.localized(obj, 'content'))

    def get_meta_title(self, obj):
        return obj.meta_title or self.get_title(obj)

    def get_meta_description(self, obj):
        return obj.meta_description or self.get_short_description(obj)


# ── SUBMISSIONS (WRITE) ─────────────────────────────────────────────────────
class SubmissionMixin(serializers.Serializer):
    # Hidden honeypot field: real users leave it empty, bots usually fill it in
    website = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def is_bot(self):
        return bool(self.initial_data.get('website'))

    def t(self, key, **kwargs):
        return translate(key, self.context.get('lang', 'en'), **kwargs)

    def validate_phone_value(self, value):
        if value and not PHONE_REGEX.match(value):
            raise serializers.ValidationError(self.t('phone_invalid'))
        return value


class EnquirySerializer(SubmissionMixin, serializers.ModelSerializer):
    full_name = serializers.CharField(required=False, allow_blank=True, write_only=True, max_length=300)
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    source = serializers.ChoiceField(choices=Enquiry.SOURCE_CHOICES, default=Enquiry.SOURCE_CONTACT)

    class Meta:
        model = Enquiry
        fields = ['id', 'source', 'full_name', 'first_name', 'last_name', 'company_name', 'phone', 'email',
                  'message', 'website', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_phone(self, value):
        return self.validate_phone_value(value.strip())

    def validate(self, attrs):
        attrs.pop('website', None)
        full_name = attrs.pop('full_name', '').strip()
        # Footer form sends a single "full_name"; contact page sends first/last names
        if full_name and not attrs.get('first_name'):
            attrs['first_name'] = full_name
        if not attrs.get('first_name', '').strip():
            field = 'full_name' if attrs['source'] == Enquiry.SOURCE_FOOTER else 'first_name'
            raise serializers.ValidationError({field: self.t('required')})
        if attrs['source'] == Enquiry.SOURCE_CONTACT and not attrs.get('last_name', '').strip():
            raise serializers.ValidationError({'last_name': self.t('required')})
        if not attrs.get('message', '').strip() and attrs['source'] == Enquiry.SOURCE_FOOTER:
            raise serializers.ValidationError({'message': self.t('required')})
        return attrs


class CareerApplicationSerializer(SubmissionMixin, serializers.ModelSerializer):
    class Meta:
        model = CareerApplication
        fields = ['id', 'first_name', 'last_name', 'email', 'mobile', 'current_location', 'nationality',
                  'education', 'degree', 'cv', 'website', 'created_at']
        read_only_fields = ['id', 'created_at']
        extra_kwargs = {'cv': {'write_only': True}}

    def validate_mobile(self, value):
        value = self.validate_phone_value(value.strip())
        if not value:
            raise serializers.ValidationError(self.t('required'))
        return value

    def validate_cv(self, file):
        max_mb = settings.CV_MAX_SIZE_MB
        if file.size > max_mb * 1024 * 1024:
            raise serializers.ValidationError(self.t('cv_size', size=max_mb))
        ext = file.name.rsplit('.', 1)[-1].lower() if '.' in file.name else ''
        if ext not in CareerApplication.CV_EXTENSIONS:
            raise serializers.ValidationError(self.t('cv_type'))
        head = file.read(8)
        file.seek(0)
        # PDF -> %PDF, DOCX -> PK zip, DOC -> OLE2 header
        if not (head.startswith(b'%PDF') or head.startswith(b'PK') or head.startswith(b'\xd0\xcf\x11\xe0')):
            raise serializers.ValidationError(self.t('cv_invalid'))
        return file

    def validate(self, attrs):
        attrs.pop('website', None)
        return attrs
