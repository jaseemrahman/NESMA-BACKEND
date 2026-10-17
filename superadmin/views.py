import datetime
import uuid

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.views import View

from superadmin.context_processors import clear_sidebar_counts
from superadmin.helper import absolute_media_url, excel_response, filter_by_status, paginate, renderhelper
from superadmin.models import Blog, BlogCategory, CareerApplication, Enquiry, optimize_image, validate_image

# Models that the generic AJAX status / sequence handlers may touch
TOGGLEABLE_MODELS = {'Blog': Blog, 'BlogCategory': BlogCategory}
MAX_IMAGE_MB = 10


class AdminView(LoginRequiredMixin, View):
    login_url = 'superadmin:login'


# ── AUTH & DASHBOARD ────────────────────────────────────────────────────────
class LoginPageView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('superadmin:Dashboard')
        return renderhelper(request, 'login', 'login', {})

    def post(self, request):
        email = request.POST.get('email', '').lower().strip()
        password = request.POST.get('password', '').strip()

        user_obj = User.objects.filter(email__iexact=email).only('username').first()
        username = user_obj.username if user_obj else email
        user = authenticate(request, username=username, password=password)

        if user is not None and user.is_active and user.is_staff:
            login(request, user)
            next_url = request.GET.get('next', '')
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            return redirect('superadmin:Dashboard')

        messages.error(request, 'Invalid email or password.')
        return renderhelper(request, 'login', 'login', {'email': email})


class Logout(AdminView):
    def get(self, request):
        logout(request)
        return redirect('superadmin:login')


class Dashboard(AdminView):
    def get(self, request):
        today = timezone.localdate()
        month_start = timezone.make_aware(datetime.datetime(today.year, today.month, 1))
        # One LEFT JOIN query for category + blog counts
        blog_stats = BlogCategory.objects.aggregate(
            categories=Count('id', filter=Q(is_active=True), distinct=True),
            total=Count('blogs'),
            active=Count('blogs', filter=Q(blogs__is_active=True)),
        )
        enquiry_stats = Enquiry.objects.aggregate(
            total=Count('id'),
            unread=Count('id', filter=Q(is_read=False)),
            footer=Count('id', filter=Q(source=Enquiry.SOURCE_FOOTER)),
            contact=Count('id', filter=Q(source=Enquiry.SOURCE_CONTACT)),
        )
        career_stats = CareerApplication.objects.aggregate(
            total=Count('id'),
            new=Count('id', filter=Q(status=CareerApplication.STATUS_NEW)),
            this_month=Count('id', filter=Q(created_at__gte=month_start)),
        )
        context = {
            'path': 'dashboard',
            'today_date': today,
            'blog_stats': blog_stats,
            'enquiry_stats': enquiry_stats,
            'career_stats': career_stats,
            'recent_enquiries': Enquiry.objects.only(
                'first_name', 'last_name', 'email', 'source', 'is_read', 'created_at'
            )[:6],
            'recent_applications': CareerApplication.objects.only(
                'first_name', 'last_name', 'email', 'degree', 'status', 'created_at'
            )[:6],
        }
        return renderhelper(request, 'dashboard', 'index', context)


class StatusToggleView(AdminView):
    """
    AJAX view to toggle is_active status for whitelisted models.
    """
    def post(self, request):
        model = TOGGLEABLE_MODELS.get(request.POST.get('model_name', ''))
        if model is None:
            return JsonResponse({'status': 'error', 'message': 'Invalid model.'}, status=400)
        obj = get_object_or_404(model, id=request.POST.get('id'))
        obj.is_active = request.POST.get('status', 'false').lower() == 'true'
        obj.save(update_fields=['is_active', 'updated_at'])
        return JsonResponse({'status': 'success', 'is_active': obj.is_active})


class SequenceUpdateView(AdminView):
    """
    AJAX view to update sequence order for whitelisted models.
    """
    def post(self, request):
        model = TOGGLEABLE_MODELS.get(request.POST.get('model_name', ''))
        if model is None:
            return JsonResponse({'status': 'error', 'message': 'Invalid model.'}, status=400)
        try:
            sequence = max(int(request.POST.get('sequence', '0')), 0)
        except ValueError:
            return JsonResponse({'status': 'error', 'message': 'Invalid sequence.'}, status=400)
        obj = get_object_or_404(model, id=request.POST.get('id'))
        obj.sequence = sequence
        obj.save(update_fields=['sequence', 'updated_at'])
        return JsonResponse({'status': 'success', 'sequence': obj.sequence})


# ── BLOG CATEGORIES MODULE ──────────────────────────────────────────────────
class BlogCategoryList(AdminView):
    def get(self, request):
        search = request.GET.get('search', '').strip()
        status_filter = request.GET.get('status', 'active').lower()

        queryset = filter_by_status(BlogCategory.objects.annotate(blog_count=Count('blogs')), status_filter)
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(name_ar__icontains=search))

        categories = paginate(request, queryset.order_by('sequence', 'name'))
        context = {
            'path': 'blog_categories',
            'categories': categories,
            'search': search,
            'status_filter': status_filter,
            'sequence_range': range(1, max(categories.paginator.count, 1) + 1),
        }
        return renderhelper(request, 'blogs', 'category_list', context)


class BlogCategoryAdd(AdminView):
    def get(self, request, id=None):
        category = get_object_or_404(BlogCategory, id=id) if id else None
        return renderhelper(request, 'blogs', 'category_add', {'path': 'blog_categories', 'category': category})

    def post(self, request, id=None):
        category = get_object_or_404(BlogCategory, id=id) if id else BlogCategory()
        name = request.POST.get('name', '').strip()
        name_ar = request.POST.get('name_ar', '').strip()

        def error(msg):
            messages.error(request, msg)
            category.name, category.name_ar = name, name_ar
            return renderhelper(request, 'blogs', 'category_add', {'path': 'blog_categories', 'category': category})

        if not name:
            return error('Category name (English) is required.')
        slug = category.slug or slugify(name)[:170]
        if not slug:
            return error('Category name must contain English letters or numbers (used for the URL slug).')
        if BlogCategory.objects.filter(Q(name__iexact=name) | Q(slug=slug)).exclude(id=category.id).exists():
            return error('A blog category with this name already exists.')

        category.slug = slug
        category.name = name
        category.name_ar = name_ar
        if not id:
            category.sequence = (BlogCategory.objects.count() or 0) + 1
        category.save()
        messages.success(request, 'Blog category saved successfully!')
        return redirect('superadmin:BlogCategoryList')


class BlogCategoryDelete(AdminView):
    def post(self, request, id):
        category = get_object_or_404(BlogCategory, id=id)
        try:
            category.delete()
            messages.success(request, 'Blog category deleted successfully.')
        except ProtectedError:
            messages.error(request, 'This category has blogs. Move or delete those blogs first.')
        return redirect('superadmin:BlogCategoryList')


# ── BLOG MODULE ─────────────────────────────────────────────────────────────
class BlogList(AdminView):
    def get(self, request):
        search = request.GET.get('search', '').strip()
        status_filter = request.GET.get('status', 'active').lower()
        category_filter = request.GET.get('category', '').strip()

        queryset = filter_by_status(
            Blog.objects.select_related('category').only(
                'title', 'title_ar', 'image', 'location', 'date', 'sequence', 'is_active', 'slug', 'category__name'
            ),
            status_filter,
        )
        if search:
            queryset = queryset.filter(Q(title__icontains=search) | Q(title_ar__icontains=search))
        if category_filter.isdigit():
            queryset = queryset.filter(category_id=category_filter)

        blogs = paginate(request, queryset)
        context = {
            'path': 'blogs',
            'blogs': blogs,
            'categories': BlogCategory.objects.filter(is_active=True).only('name'),
            'search': search,
            'status_filter': status_filter,
            'category_filter': category_filter,
            'sequence_range': range(1, max(blogs.paginator.count, 1) + 1),
        }
        return renderhelper(request, 'blogs', 'list', context)


class BlogAdd(AdminView):
    TEXT_FIELDS = (
        'title', 'title_ar', 'location', 'location_ar', 'short_description', 'short_description_ar',
        'content', 'content_ar', 'meta_title', 'meta_description',
    )

    def render_form(self, request, blog):
        context = {
            'path': 'blogs',
            'blog': blog,
            'categories': BlogCategory.objects.filter(is_active=True).only('name', 'name_ar'),
        }
        return renderhelper(request, 'blogs', 'add', context)

    def get(self, request, id=None):
        blog = get_object_or_404(Blog, id=id) if id else None
        return self.render_form(request, blog)

    def post(self, request, id=None):
        blog = get_object_or_404(Blog, id=id) if id else Blog()

        for field in self.TEXT_FIELDS:
            setattr(blog, field, request.POST.get(field, '').strip())
        blog.category_id = request.POST.get('category') or None
        # URL slug: admin input, otherwise generated from the English title
        blog.slug = slugify(request.POST.get('slug', '').strip() or blog.title)[:255]
        date = request.POST.get('date')
        try:
            blog.date = datetime.date.fromisoformat(date) if date else timezone.localdate()
        except ValueError:
            blog.date = timezone.localdate()
        errors = []
        upload = request.FILES.get('image')
        if upload:
            if upload.size > MAX_IMAGE_MB * 1024 * 1024:
                errors.append(f'Image must be under {MAX_IMAGE_MB} MB.')
            elif not validate_image(upload):
                errors.append('Uploaded file is not a valid image.')
            else:
                blog.image = upload

        if not blog.title or not blog.category_id:
            errors.append('Title (English) and Category are required.')
        if not blog.content or blog.content in ('<p><br></p>', '<br>'):
            errors.append('Content (English) is required.')
        if not blog.image:
            errors.append('Featured image is required.')
        if blog.title and not blog.slug:
            errors.append('URL slug is empty - enter an English slug.')
        elif blog.slug and Blog.objects.filter(slug=blog.slug).exclude(id=blog.id).exists():
            errors.append(f'The URL slug "{blog.slug}" is already used by another blog. Please change the slug.')
        if errors:
            for e in errors:
                messages.error(request, e)
            return self.render_form(request, blog)

        if not id:
            blog.sequence = Blog.objects.count() + 1
        blog.save()
        messages.success(request, 'Blog saved successfully!')
        return redirect('superadmin:BlogList')


class BlogDelete(AdminView):
    def post(self, request, id):
        get_object_or_404(Blog, id=id).delete()
        messages.success(request, 'Blog deleted successfully.')
        return redirect('superadmin:BlogList')


class EditorImageUpload(AdminView):
    """
    Summernote image upload: stores the file in media (instead of base64 inside the blog HTML)
    and returns its absolute https URL.
    """
    def post(self, request):
        upload = request.FILES.get('file')
        if not upload:
            return JsonResponse({'status': 'error', 'message': 'No file uploaded.'}, status=400)
        if upload.size > MAX_IMAGE_MB * 1024 * 1024:
            return JsonResponse({'status': 'error', 'message': f'Image must be under {MAX_IMAGE_MB} MB.'}, status=400)
        if not validate_image(upload):
            return JsonResponse({'status': 'error', 'message': 'Uploaded file is not a valid image.'}, status=400)
        ext = upload.name.rsplit('.', 1)[-1].lower() if '.' in upload.name else 'jpg'
        content = optimize_image(upload) or upload
        name = default_storage.save(f'blogs/content/{timezone.now():%Y/%m}/{uuid.uuid4().hex}.{ext}', content)
        return JsonResponse({'status': 'success', 'url': absolute_media_url(default_storage.url(name))})


# ── ENQUIRIES MODULE ────────────────────────────────────────────────────────
def enquiry_queryset(request):
    search = request.GET.get('search', '').strip()
    source = request.GET.get('source', '').strip()
    read_filter = request.GET.get('read', '').strip()

    queryset = Enquiry.objects.all()
    if search:
        queryset = queryset.filter(
            Q(first_name__icontains=search) | Q(last_name__icontains=search) | Q(email__icontains=search)
            | Q(phone__icontains=search) | Q(company_name__icontains=search)
        )
    if source in dict(Enquiry.SOURCE_CHOICES):
        queryset = queryset.filter(source=source)
    if read_filter == 'unread':
        queryset = queryset.filter(is_read=False)
    elif read_filter == 'read':
        queryset = queryset.filter(is_read=True)
    return queryset, {'search': search, 'source_filter': source, 'read_filter': read_filter}


class EnquiryList(AdminView):
    def get(self, request):
        queryset, filters = enquiry_queryset(request)
        context = {
            'path': 'enquiries',
            'enquiries': paginate(request, queryset),
            'source_choices': Enquiry.SOURCE_CHOICES,
            **filters,
        }
        return renderhelper(request, 'enquiries', 'list', context)


class EnquiryMarkRead(AdminView):
    """AJAX: mark an enquiry as read / unread (called when the detail modal is opened)."""
    def post(self, request, id):
        is_read = request.POST.get('is_read', 'true').lower() == 'true'
        updated = Enquiry.objects.filter(id=id).update(is_read=is_read)
        if not updated:
            raise Http404
        clear_sidebar_counts()
        return JsonResponse({'status': 'success', 'is_read': is_read})


class EnquiryDelete(AdminView):
    def post(self, request, id):
        get_object_or_404(Enquiry, id=id).delete()
        messages.success(request, 'Enquiry deleted successfully.')
        return redirect('superadmin:EnquiryList')


class EnquiryExport(AdminView):
    def get(self, request):
        queryset, _ = enquiry_queryset(request)
        rows = (
            (e.id, e.get_source_display(), e.first_name, e.last_name, e.company_name, e.phone, e.email,
             e.message, e.get_language_display(), 'Yes' if e.is_read else 'No',
             timezone.localtime(e.created_at).strftime('%d/%m/%Y %I:%M %p'))
            for e in queryset.iterator(chunk_size=500)
        )
        headers = ['ID', 'Source', 'First Name', 'Last Name', 'Company', 'Phone', 'Email', 'Message',
                   'Language', 'Read', 'Submitted At']
        return excel_response('enquiries', headers, rows)


# ── CAREER APPLICATIONS MODULE ──────────────────────────────────────────────
def career_queryset(request):
    search = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()
    education = request.GET.get('education', '').strip()

    queryset = CareerApplication.objects.defer('admin_notes')
    if search:
        queryset = queryset.filter(
            Q(first_name__icontains=search) | Q(last_name__icontains=search) | Q(email__icontains=search)
            | Q(mobile__icontains=search) | Q(degree__icontains=search) | Q(current_location__icontains=search)
        )
    if status_filter in dict(CareerApplication.STATUS_CHOICES):
        queryset = queryset.filter(status=status_filter)
    if education in dict(CareerApplication.EDUCATION_CHOICES):
        queryset = queryset.filter(education=education)
    return queryset, {'search': search, 'status_filter': status_filter, 'education_filter': education}


class CareerApplicationList(AdminView):
    def get(self, request):
        queryset, filters = career_queryset(request)
        context = {
            'path': 'careers',
            'applications': paginate(request, queryset),
            'status_choices': CareerApplication.STATUS_CHOICES,
            'education_choices': CareerApplication.EDUCATION_CHOICES,
            **filters,
        }
        return renderhelper(request, 'careers', 'list', context)


class CareerApplicationDetail(AdminView):
    def get(self, request, id):
        application = get_object_or_404(CareerApplication, id=id)
        context = {
            'path': 'careers',
            'application': application,
            'status_choices': CareerApplication.STATUS_CHOICES,
        }
        return renderhelper(request, 'careers', 'detail', context)

    def post(self, request, id):
        application = get_object_or_404(CareerApplication, id=id)
        status = request.POST.get('status', '')
        if status in dict(CareerApplication.STATUS_CHOICES):
            application.status = status
        application.admin_notes = request.POST.get('admin_notes', '').strip()
        application.save(update_fields=['status', 'admin_notes', 'updated_at'])
        messages.success(request, 'Application updated successfully!')
        return redirect('superadmin:CareerApplicationDetail', id=id)


class CareerApplicationStatus(AdminView):
    """AJAX: quick status change from the list page."""
    def post(self, request, id):
        status = request.POST.get('status', '')
        if status not in dict(CareerApplication.STATUS_CHOICES):
            return JsonResponse({'status': 'error', 'message': 'Invalid status.'}, status=400)
        updated = CareerApplication.objects.filter(id=id).update(status=status, updated_at=timezone.now())
        if not updated:
            raise Http404
        clear_sidebar_counts()
        return JsonResponse({'status': 'success'})


class CareerApplicationCV(AdminView):
    """Serve CV files only to logged-in admins."""
    def get(self, request, id):
        application = get_object_or_404(CareerApplication.objects.only('cv', 'first_name', 'last_name'), id=id)
        if not application.cv:
            raise Http404
        try:
            handle = application.cv.open('rb')
        except FileNotFoundError:
            raise Http404
        ext = application.cv.name.rsplit('.', 1)[-1].lower()
        download_name = f"CV_{application.full_name.replace(' ', '_')}.{ext}"
        inline = ext == 'pdf' and request.GET.get('download') != '1'
        return FileResponse(handle, as_attachment=not inline, filename=download_name)


class CareerApplicationDelete(AdminView):
    def post(self, request, id):
        application = get_object_or_404(CareerApplication, id=id)
        application.cv.delete(save=False)
        application.delete()
        messages.success(request, 'Career application deleted successfully.')
        return redirect('superadmin:CareerApplicationList')


class CareerApplicationExport(AdminView):
    def get(self, request):
        queryset, _ = career_queryset(request)
        base = request.build_absolute_uri('/')[:-1]
        rows = (
            (a.id, a.first_name, a.last_name, a.email, a.mobile, a.current_location, a.nationality,
             a.education, a.degree, a.get_status_display(), a.get_language_display(),
             f'{base}/superadmin/Career-Application-CV/{a.id}',
             timezone.localtime(a.created_at).strftime('%d/%m/%Y %I:%M %p'))
            for a in queryset.iterator(chunk_size=500)
        )
        headers = ['ID', 'First Name', 'Last Name', 'Email', 'Mobile', 'Current Location', 'Nationality',
                   'Education', 'Degree', 'Status', 'Language', 'CV Link', 'Applied At']
        return excel_response('career_applications', headers, rows)


# ── PROFILE ─────────────────────────────────────────────────────────────────
class ProfileView(AdminView):
    def get(self, request):
        return renderhelper(request, 'layout', 'profile', {'path': 'profile'})

    def post(self, request):
        old_password = request.POST.get('oldpassword', '').strip()
        new_password = request.POST.get('newpassword', '').strip()
        con_password = request.POST.get('conpassword', '').strip()

        error = None
        if not old_password or not new_password or not con_password:
            error = 'All fields are required.'
        elif new_password != con_password:
            error = 'New password and confirm password do not match.'
        elif len(new_password) < 8:
            error = 'Password must be at least 8 characters long.'
        elif not request.user.check_password(old_password):
            error = 'Incorrect current password.'

        if error:
            messages.error(request, error)
            return renderhelper(request, 'layout', 'profile', {'path': 'profile'})

        request.user.set_password(new_password)
        request.user.save()
        update_session_auth_hash(request, request.user)
        messages.success(request, 'Password updated successfully.')
        return redirect('superadmin:Dashboard')
