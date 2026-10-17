from django.db.models import Case, Exists, IntegerField, OuterRef, Q, When
from django.utils import translation
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from superadmin.helper import get_client_ip
from superadmin.models import Blog, BlogCategory, CareerApplication
from website.cache import cached_api_response
from website.helper import (
    get_language, notify_new_career_application, notify_new_enquiry, run_in_background,
)
from website.serializers import (
    BlogCategorySerializer, BlogDetailSerializer, BlogListSerializer,
    CareerApplicationSerializer, EnquirySerializer,
)

BLOG_LIST_FIELDS = (
    'id', 'slug', 'title', 'title_ar', 'location', 'location_ar', 'date', 'image',
    'short_description', 'short_description_ar',
    'category__id', 'category__name', 'category__name_ar', 'category__slug',
)

SUCCESS_MESSAGES = {
    'enquiry': {
        'en': 'Thank you for contacting us! Our team will get back to you shortly.',
        'ar': 'شكراً لتواصلك معنا! سيتواصل معك فريقنا قريباً.',
    },
    'career': {
        'en': 'Thank you for your application! Our HR team will review your profile and contact you.',
        'ar': 'شكراً لتقديم طلبك! سيقوم فريق الموارد البشرية بمراجعة ملفك والتواصل معك.',
    },
    'error': {
        'en': 'Please correct the errors below.',
        'ar': 'يرجى تصحيح الأخطاء أدناه.',
    },
}


class LanguageMixin:
    """
    Resolves `?lang=en|ar` (or Accept-Language) once and passes it to serializers.
    DRF's built-in validation messages are translated by activating the language.
    """
    def get_language(self):
        if not hasattr(self, '_lang'):
            self._lang = get_language(self.request)
        return self._lang

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['lang'] = self.get_language()
        return context

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        translation.activate(self.get_language())

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Content-Language'] = translation.get_language() or 'en'
        translation.deactivate()
        return response


# ── CONTENT ENDPOINTS (GET, cached) ─────────────────────────────────────────
class BlogCategoryListView(LanguageMixin, generics.ListAPIView):
    """
    GET /api/blog-categories/?lang=ar
    Active categories that have at least one active blog.
    """
    serializer_class = BlogCategorySerializer
    pagination_class = None

    def get_queryset(self):
        # EXISTS subquery instead of JOIN + DISTINCT
        has_blogs = Blog.objects.filter(category=OuterRef('pk'), is_active=True)
        return (
            BlogCategory.objects.filter(Exists(has_blogs), is_active=True)
            .only('id', 'name', 'name_ar', 'slug').order_by('sequence', 'name')
        )

    @cached_api_response
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class BlogListView(LanguageMixin, generics.ListAPIView):
    """
    GET /api/blogs/?lang=ar&category=<slug|id>&search=<text>&page=1&page_size=9&exclude=<slug>
    """
    serializer_class = BlogListSerializer

    def get_queryset(self):
        queryset = (
            Blog.objects.filter(is_active=True, category__is_active=True)
            .select_related('category').only(*BLOG_LIST_FIELDS)
        )
        params = self.request.query_params
        category = params.get('category', '').strip()
        if category and category.lower() != 'all':
            queryset = queryset.filter(category_id=category) if category.isdigit() else queryset.filter(category__slug=category)
        search = params.get('search', '').strip()
        if search:
            queryset = queryset.filter(Q(title__icontains=search) | Q(title_ar__icontains=search))
        exclude = params.get('exclude', '').strip()
        if exclude:
            queryset = queryset.exclude(slug=exclude)
        return queryset.order_by('sequence', '-date', '-id')

    @cached_api_response
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class BlogDetailView(LanguageMixin, generics.GenericAPIView):
    """
    GET /api/blogs/<slug>/?lang=ar
    Returns the blog plus up to 3 related posts ("Similar news & announcements").
    """
    serializer_class = BlogDetailSerializer

    @cached_api_response
    def get(self, request, slug):
        blog = (
            Blog.objects.select_related('category')
            .filter(slug=slug, is_active=True, category__is_active=True).first()
        )
        if blog is None:
            message = 'المقال غير موجود.' if self.get_language() == 'ar' else 'Blog not found.'
            return Response({'status': 'error', 'message': message}, status=status.HTTP_404_NOT_FOUND)
        context = self.get_serializer_context()
        related = (
            Blog.objects.filter(is_active=True, category__is_active=True).exclude(pk=blog.pk)
            .select_related('category').only(*BLOG_LIST_FIELDS)
            .annotate(same_category=Case(When(category_id=blog.category_id, then=0), default=1, output_field=IntegerField()))
            .order_by('same_category', '-date', '-id')[:3]
        )
        data = BlogDetailSerializer(blog, context=context).data
        data['related'] = BlogListSerializer(related, many=True, context=context).data
        return Response(data)


class CareerOptionsView(LanguageMixin, APIView):
    """
    GET /api/career-options/?lang=ar - dropdown values for the careers form.
    """
    EDUCATION_AR = {
        'High School': 'الثانوية العامة',
        'Diploma': 'دبلوم',
        "Bachelor's Degree": 'بكالوريوس',
        "Master's Degree": 'ماجستير',
        'PhD': 'دكتوراه',
    }

    def get(self, request):
        lang = self.get_language()
        education = [
            {'value': value, 'label': self.EDUCATION_AR[value] if lang == 'ar' else label}
            for value, label in CareerApplication.EDUCATION_CHOICES
        ]
        response = Response({'education': education})
        response['Cache-Control'] = 'public, max-age=3600'
        return response


# ── SUBMISSION ENDPOINTS (POST) ─────────────────────────────────────────────
class BaseSubmissionView(LanguageMixin, generics.CreateAPIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'submissions'
    message_key = ''
    notify = None

    def create(self, request, *args, **kwargs):
        lang = self.get_language()
        serializer = self.get_serializer(data=request.data)

        # Honeypot: pretend success, store nothing
        if serializer.is_bot():
            return Response({'status': 'success', 'message': SUCCESS_MESSAGES[self.message_key][lang]},
                            status=status.HTTP_201_CREATED)

        if not serializer.is_valid():
            return Response({
                'status': 'error',
                'message': SUCCESS_MESSAGES['error'][lang],
                'errors': serializer.errors,
            }, status=status.HTTP_400_BAD_REQUEST)

        instance = serializer.save(language=lang, ip_address=get_client_ip(request))
        run_in_background(type(self).notify, instance.pk)
        return Response({
            'status': 'success',
            'message': SUCCESS_MESSAGES[self.message_key][lang],
            'data': {'id': instance.pk},
        }, status=status.HTTP_201_CREATED)


class EnquiryCreateView(BaseSubmissionView):
    """
    POST /api/enquiry/
    Footer:  {source: "footer", full_name, email, message}
    Contact: {source: "contact", first_name, last_name, company_name, phone, email, message}
    """
    serializer_class = EnquirySerializer
    message_key = 'enquiry'
    notify = staticmethod(notify_new_enquiry)


class CareerApplicationCreateView(BaseSubmissionView):
    """
    POST /api/career-application/  (multipart/form-data)
    {first_name, last_name, email, mobile, current_location, nationality, education, degree, cv}
    """
    serializer_class = CareerApplicationSerializer
    message_key = 'career'
    notify = staticmethod(notify_new_career_application)
