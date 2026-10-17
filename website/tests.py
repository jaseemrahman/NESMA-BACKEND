import io
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image
from rest_framework.test import APIClient

from superadmin.models import Blog, BlogCategory, CareerApplication, Enquiry

TEMP_MEDIA = tempfile.mkdtemp()


def make_image(name='test.png'):
    buffer = io.BytesIO()
    Image.new('RGB', (2400, 1200), (46, 54, 143)).save(buffer, format='PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


def make_photo_jpeg(name='photo.jpg', size=(1600, 1000)):
    # Noisy gradient so the JPEG behaves like a real photo
    img = Image.effect_noise(size, 60).convert('RGB')
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=92)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/jpeg')


def make_pdf(name='cv.pdf'):
    return SimpleUploadedFile(name, b'%PDF-1.4\n%test cv\n', content_type='application/pdf')


@override_settings(
    MEDIA_ROOT=TEMP_MEDIA,
    MEDIA_DOMAIN='http://api.nesma-nit.com',
    ASYNC_NOTIFICATIONS=False,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    REST_FRAMEWORK={
        'DEFAULT_AUTHENTICATION_CLASSES': [],
        'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.AllowAny'],
        'UNAUTHENTICATED_USER': None,
        'DEFAULT_PAGINATION_CLASS': 'website.pagination.StandardPagination',
        'PAGE_SIZE': 9,
        'DEFAULT_THROTTLE_RATES': {'submissions': '1000/hour'},
    },
)
class WebsiteAPITests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.news = BlogCategory.objects.get(slug='news')
        self.announcement = BlogCategory.objects.get(slug='announcement')
        self.blog = Blog.objects.create(
            category=self.news, title='NIT Signs a Contract Valued at Over SAR 160 Million',
            title_ar='نسما توقع عقداً بقيمة 160 مليون ريال', location='Riyadh, Saudi Arabia',
            location_ar='الرياض', content='<p>English body</p>', content_ar='<p>محتوى عربي</p>',
            image=make_image(),
        )
        self.other = Blog.objects.create(
            category=self.announcement, title='SEC Jubail Contract', content='<p>Body</p>', image=make_image(),
        )

    # ── Content ──────────────────────────────────────────────────────────────
    def test_seeded_categories_and_only_used_ones_are_listed(self):
        self.assertEqual(BlogCategory.objects.count(), 4)
        res = self.client.get('/api/blog-categories/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual({c['slug'] for c in res.json()}, {'news', 'announcement'})

    def test_blog_list_english_and_arabic(self):
        res = self.client.get('/api/blogs/')
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body['count'], 2)
        item = next(b for b in body['results'] if b['id'] == self.blog.id)
        self.assertEqual(item['category']['name'], 'News')
        self.assertTrue(item['formatted_date'].isupper())
        # Full URL, forced to https, original format kept
        self.assertTrue(item['image'].startswith('https://api.nesma-nit.com/media/blogs/'), item['image'])
        self.assertTrue(item['image'].endswith('.png'))

        res = self.client.get('/api/blogs/?lang=ar')
        item = next(b for b in res.json()['results'] if b['id'] == self.blog.id)
        self.assertEqual(item['title'], self.blog.title_ar)
        self.assertEqual(item['category']['name'], 'أخبار')
        # Missing Arabic falls back to English
        other = next(b for b in res.json()['results'] if b['id'] == self.other.id)
        self.assertEqual(other['title'], 'SEC Jubail Contract')

    def test_accept_language_header(self):
        res = self.client.get('/api/blogs/', HTTP_ACCEPT_LANGUAGE='ar-SA,ar;q=0.9')
        item = next(b for b in res.json()['results'] if b['id'] == self.blog.id)
        self.assertEqual(item['title'], self.blog.title_ar)

    def test_blog_filter_by_category_slug(self):
        res = self.client.get('/api/blogs/?category=announcement')
        self.assertEqual([b['id'] for b in res.json()['results']], [self.other.id])

    def test_blog_detail_by_slug_with_related(self):
        res = self.client.get(f'/api/blogs/{self.blog.slug}/?lang=ar')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['content'], '<p>محتوى عربي</p>')
        self.assertEqual([r['id'] for r in data['related']], [self.other.id])

    def test_inactive_blog_is_hidden(self):
        self.blog.is_active = False
        self.blog.save()
        res = self.client.get(f'/api/blogs/{self.blog.slug}/?lang=ar')
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json(), {'status': 'error', 'message': 'المقال غير موجود.'})

    def test_cache_is_invalidated_on_save(self):
        self.client.get('/api/blogs/')
        with self.assertNumQueries(0):
            self.client.get('/api/blogs/')
        self.blog.title = 'Updated Title'
        self.blog.save()
        res = self.client.get('/api/blogs/')
        self.assertIn('Updated Title', [b['title'] for b in res.json()['results']])

    def test_list_query_count_is_constant(self):
        for i in range(5):
            Blog.objects.create(category=self.news, title=f'Post {i}', content='x', image=make_image())
        cache.clear()
        # version lookup + count + page query (category joined via select_related)
        with self.assertNumQueries(2):
            res = self.client.get('/api/blogs/?page_size=3')
        body = res.json()
        self.assertEqual((body['total_pages'], body['next_page'], body['previous_page']), (3, 2, None))
        # Unknown params don't create new cache entries
        with self.assertNumQueries(0):
            self.client.get('/api/blogs/?page_size=3&utm_source=x')

    def test_categories_endpoint_single_query(self):
        with self.assertNumQueries(1):
            self.client.get('/api/blog-categories/')

    def test_detail_two_queries(self):
        with self.assertNumQueries(2):
            self.client.get(f'/api/blogs/{self.blog.slug}/')

    def test_content_media_links_are_absolute_https(self):
        self.blog.content = '<p><img src="/media/blogs/content/a.jpg"> <img src="http://127.0.0.1:8000/media/b.png"></p>'
        self.blog.save()
        content = self.client.get(f'/api/blogs/{self.blog.slug}/').json()['content']
        self.assertIn('src="https://api.nesma-nit.com/media/blogs/content/a.jpg"', content)
        self.assertIn('src="https://api.nesma-nit.com/media/b.png"', content)

    def test_media_url_kept_http_only_for_localhost(self):
        from superadmin.helper import absolute_media_url
        with self.settings(MEDIA_DOMAIN='http://127.0.0.1:8000'):
            self.assertEqual(absolute_media_url('/media/x.jpg'), 'http://127.0.0.1:8000/media/x.jpg')
        with self.settings(MEDIA_DOMAIN='api.nesma-nit.com'):
            self.assertEqual(absolute_media_url('/media/x.jpg'), 'https://api.nesma-nit.com/media/x.jpg')

    # ── Enquiry ──────────────────────────────────────────────────────────────
    def test_footer_enquiry(self):
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post('/api/enquiry/', {
                'source': 'footer', 'full_name': 'Ahmed Ali', 'email': 'ahmed@example.com', 'message': 'Hello',
            }, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        enquiry = Enquiry.objects.get()
        self.assertEqual((enquiry.first_name, enquiry.source), ('Ahmed Ali', 'footer'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].reply_to, ['ahmed@example.com'])
        self.assertIn('Footer Form', mail.outbox[0].subject)

    def test_contact_enquiry_requires_last_name_and_sends_email(self):
        payload = {'source': 'contact', 'first_name': 'Sara', 'email': 'sara@example.com', 'phone': '+966 55 063 4599'}
        res = self.client.post('/api/enquiry/', payload, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('last_name', res.json()['errors'])

        payload.update(last_name='Khan', company_name='ACME', message='Need a quote')
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            res = self.client.post('/api/enquiry/?lang=ar', payload, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Enquiry.objects.get().language, 'ar')
        self.assertEqual(len(callbacks), 1)

    def test_enquiry_arabic_validation_messages(self):
        res = self.client.post('/api/enquiry/?lang=ar', {'source': 'contact', 'email': 'bad'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()['message'], 'يرجى تصحيح الأخطاء أدناه.')

    def test_honeypot_stores_nothing(self):
        res = self.client.post('/api/enquiry/', {
            'source': 'footer', 'full_name': 'Bot', 'email': 'bot@example.com', 'message': 'spam', 'website': 'x',
        }, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertFalse(Enquiry.objects.exists())

    def test_invalid_phone(self):
        res = self.client.post('/api/enquiry/', {
            'source': 'contact', 'first_name': 'A', 'last_name': 'B', 'email': 'a@b.com', 'phone': 'abc',
        }, format='json')
        self.assertIn('phone', res.json()['errors'])

    # ── Career application ──────────────────────────────────────────────────
    def career_payload(self, **overrides):
        payload = {
            'first_name': 'Omar', 'last_name': 'Hassan', 'email': 'omar@example.com', 'mobile': '+966550000000',
            'current_location': 'Jeddah', 'nationality': 'Saudi Arabian', 'education': "Bachelor's Degree",
            'degree': 'Electrical Engineering', 'cv': make_pdf(),
        }
        payload.update(overrides)
        return payload

    def test_career_application_with_cv_email_attachment(self):
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post('/api/career-application/', self.career_payload(), format='multipart')
        self.assertEqual(res.status_code, 201, res.content)
        self.assertTrue(CareerApplication.objects.exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['jaseemrahmanjr@gmail.com'])
        self.assertEqual(len(mail.outbox[0].attachments), 1)

    def test_career_application_rejects_bad_cv(self):
        fake = SimpleUploadedFile('cv.pdf', b'not really a pdf', content_type='application/pdf')
        res = self.client.post('/api/career-application/', self.career_payload(cv=fake), format='multipart')
        self.assertEqual(res.status_code, 400)
        self.assertIn('cv', res.json()['errors'])

        exe = SimpleUploadedFile('cv.exe', b'MZ...', content_type='application/octet-stream')
        res = self.client.post('/api/career-application/', self.career_payload(cv=exe), format='multipart')
        self.assertIn('cv', res.json()['errors'])

    def test_career_required_fields(self):
        res = self.client.post('/api/career-application/', {'first_name': 'X'}, format='multipart')
        self.assertEqual(res.status_code, 400)
        for field in ('email', 'mobile', 'current_location', 'education', 'degree', 'cv'):
            self.assertIn(field, res.json()['errors'])

    def test_career_options(self):
        res = self.client.get('/api/career-options/?lang=ar')
        self.assertEqual(res.json()['education'][0]['label'], 'الثانوية العامة')

    def test_cors_header_for_frontend(self):
        res = self.client.get('/api/blogs/', HTTP_ORIGIN='https://nit-hazel.vercel.app')
        self.assertEqual(res['Access-Control-Allow-Origin'], '*')  # all origins allowed


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class SuperadminTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('admin', 'admin@nit.com', 'StrongPass#2026', is_staff=True)
        self.client.login(username='admin', password='StrongPass#2026')
        self.news = BlogCategory.objects.get(slug='news')

    def test_login_with_email(self):
        self.client.logout()
        res = self.client.post(reverse('superadmin:login'), {'email': 'admin@nit.com', 'password': 'StrongPass#2026'})
        self.assertRedirects(res, reverse('superadmin:Dashboard'))

    def test_non_staff_cannot_login(self):
        User.objects.create_user('user', 'user@nit.com', 'StrongPass#2026')
        self.client.logout()
        res = self.client.post(reverse('superadmin:login'), {'email': 'user@nit.com', 'password': 'StrongPass#2026'})
        self.assertEqual(res.status_code, 200)

    def test_all_pages_render(self):
        blog = Blog.objects.create(category=self.news, title='Hello', content='x', image=make_image())
        enquiry = Enquiry.objects.create(first_name='A', email='a@b.com', message='<script>x</script>')
        application = CareerApplication.objects.create(
            first_name='O', email='o@b.com', mobile='1234567', current_location='J', education='PhD',
            degree='CS', cv=make_pdf(),
        )
        urls = [
            reverse('superadmin:Dashboard'), reverse('superadmin:BlogCategoryList'),
            reverse('superadmin:BlogCategoryAdd'), reverse('superadmin:BlogCategoryEdit', args=[self.news.id]),
            reverse('superadmin:BlogList'), reverse('superadmin:BlogAdd'), reverse('superadmin:BlogEdit', args=[blog.id]),
            reverse('superadmin:EnquiryList'), reverse('superadmin:CareerApplicationList'),
            reverse('superadmin:CareerApplicationDetail', args=[application.id]), reverse('superadmin:Profile'),
            reverse('superadmin:EnquiryExport'), reverse('superadmin:CareerApplicationExport'),
            reverse('superadmin:CareerApplicationCV', args=[application.id]),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertNotContains(self.client.get(reverse('superadmin:EnquiryList')), '<script>x</script>')
        self.assertEqual(self.client.get(reverse('superadmin:BlogDetail', args=[blog.id])).status_code, 200)

    def test_create_blog_from_admin(self):
        res = self.client.post(reverse('superadmin:BlogAdd'), {
            'title': 'New Substation Project', 'title_ar': 'مشروع محطة جديدة', 'category': self.news.id,
            'content': '<p>Body</p>', 'content_ar': '<p>محتوى</p>', 'date': '2026-03-12', 'image': make_image(),
        })
        self.assertRedirects(res, reverse('superadmin:BlogList'))
        blog = Blog.objects.get()
        self.assertEqual(blog.slug, 'new-substation-project')
        self.assertTrue(blog.image.name.endswith('.png'))
        with Image.open(blog.image.path) as img:
            self.assertEqual(img.size, (2400, 1200))  # resolution untouched

    def test_jpeg_optimisation_is_visually_lossless(self):
        from PIL import ImageChops, ImageStat
        upload = make_photo_jpeg()
        original = Image.open(io.BytesIO(upload.read())).convert('RGB')
        upload.seek(0)
        blog = Blog.objects.create(category=self.news, title='Photo', content='x', image=upload)
        with Image.open(blog.image.path) as saved:
            self.assertEqual(saved.format, 'JPEG')
            self.assertEqual(saved.size, original.size)
            diff = ImageStat.Stat(ImageChops.difference(original, saved.convert('RGB'))).mean
        self.assertLess(max(diff), 1.0)  # mean per-channel difference below 1/255

    def test_duplicate_slug_shows_error(self):
        Blog.objects.create(category=self.news, title='Same Title', content='x', image=make_image())
        res = self.client.post(reverse('superadmin:BlogAdd'), {
            'title': 'Same Title', 'title_ar': 'عنوان', 'category': self.news.id, 'content': '<p>Body</p>',
            'content_ar': '<p>محتوى</p>', 'date': '2026-03-12', 'image': make_image(),
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Blog.objects.count(), 1)
        self.assertContains(res, 'Another blog already has this English title')

    def test_rejects_non_image_upload(self):
        fake = SimpleUploadedFile('evil.png', b'not an image', content_type='image/png')
        res = self.client.post(reverse('superadmin:BlogAdd'), {
            'title': 'Fake', 'category': self.news.id, 'content': '<p>Body</p>', 'image': fake,
        })
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Blog.objects.exists())

    @override_settings(MEDIA_DOMAIN='https://api.nesma-nit.com')
    def test_editor_image_upload(self):
        res = self.client.post(reverse('superadmin:EditorImageUpload'), {'file': make_photo_jpeg()})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['url'].startswith('https://api.nesma-nit.com/media/blogs/content/'))

    def test_replaced_image_file_is_deleted(self):
        import os
        blog = Blog.objects.create(category=self.news, title='Swap', content='x', image=make_image())
        old_path = blog.image.path
        with self.captureOnCommitCallbacks(execute=True):
            blog.image = make_image('new.png')
            blog.save()
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(blog.image.path))

    def test_category_with_blogs_cannot_be_deleted(self):
        Blog.objects.create(category=self.news, title='Hello', content='x', image=make_image())
        self.client.post(reverse('superadmin:BlogCategoryDelete', args=[self.news.id]))
        self.assertTrue(BlogCategory.objects.filter(pk=self.news.pk).exists())

    def test_delete_requires_post(self):
        enquiry = Enquiry.objects.create(first_name='A', email='a@b.com')
        self.assertEqual(self.client.get(reverse('superadmin:EnquiryDelete', args=[enquiry.id])).status_code, 405)
        self.client.post(reverse('superadmin:EnquiryDelete', args=[enquiry.id]))
        self.assertFalse(Enquiry.objects.exists())

    def test_status_toggle_whitelist(self):
        res = self.client.post(reverse('superadmin:StatusToggle'), {'model_name': 'User', 'id': self.user.id, 'status': 'false'})
        self.assertEqual(res.status_code, 400)
        res = self.client.post(reverse('superadmin:StatusToggle'), {'model_name': 'BlogCategory', 'id': self.news.id, 'status': 'false'})
        self.assertEqual(res.json()['is_active'], False)

    def test_login_required(self):
        self.client.logout()
        res = self.client.get(reverse('superadmin:EnquiryList'))
        self.assertEqual(res.status_code, 302)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class AdminPanelBehaviourTests(TestCase):
    """Admin URL, required Arabic fields, auto slugs, exports and list filters."""

    def setUp(self):
        self.user = User.objects.create_user('admin', 'admin@nit.com', 'StrongPass#2026', is_staff=True)
        self.client.login(username='admin', password='StrongPass#2026')
        self.news = BlogCategory.objects.get(slug='news')

    def blog_payload(self, **overrides):
        payload = {
            'title': 'Grid Expansion', 'title_ar': 'توسعة الشبكة', 'category': self.news.id,
            'content': '<p>Body</p>', 'content_ar': '<p>محتوى</p>', 'date': '2026-03-12', 'image': make_image(),
        }
        payload.update(overrides)
        return payload

    # ── layout / urls ──
    def test_admin_lives_at_site_root(self):
        self.assertEqual(reverse('superadmin:login'), '/')
        self.assertEqual(reverse('superadmin:Dashboard'), '/Dashboard')
        self.client.logout()
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/superadmin/').status_code, 404)

    def test_layout_changes(self):
        html = self.client.get(reverse('superadmin:Dashboard')).content.decode()
        self.assertNotIn('ZUARAK', html.upper())
        self.assertIn('sidebar-logout', html)  # sign out pinned to sidebar bottom
        self.assertIn('Change Password', html)  # in the profile dropdown
        self.assertNotIn('side-menu__label">Change Password', html)  # not in the sidebar
        self.assertIn('admin_avatar.jpg', html)
        self.client.logout()
        self.assertNotIn('ZUARAK', self.client.get('/').content.decode().upper())

    def test_admin_pages_are_never_cached(self):
        res = self.client.get(reverse('superadmin:BlogList'))
        self.assertIn('no-cache', res['Cache-Control'])

    # ── arabic required + auto slug ──
    def test_blog_requires_arabic_title_and_content(self):
        res = self.client.post(reverse('superadmin:BlogAdd'), self.blog_payload(title_ar='', content_ar='<p><br></p>'))
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Blog.objects.exists())
        self.assertContains(res, 'Title is required in both English and Arabic')
        self.assertContains(res, 'Content is required in both English and Arabic')

    def test_blog_location_must_be_given_in_both_languages(self):
        res = self.client.post(reverse('superadmin:BlogAdd'), self.blog_payload(location='Riyadh'))
        self.assertContains(res, 'location in both English and Arabic')
        self.assertFalse(Blog.objects.exists())

    def test_category_requires_arabic_name(self):
        res = self.client.post(reverse('superadmin:BlogCategoryAdd'), {'name': 'Press', 'name_ar': ''})
        self.assertContains(res, 'both English and Arabic')
        self.assertFalse(BlogCategory.objects.filter(name='Press').exists())

    def test_slug_is_generated_and_follows_title(self):
        self.client.post(reverse('superadmin:BlogAdd'), self.blog_payload())
        blog = Blog.objects.get()
        self.assertEqual(blog.slug, 'grid-expansion')
        self.client.post(reverse('superadmin:BlogEdit', args=[blog.id]),
                         self.blog_payload(title='Grid Expansion Phase 2', image=''))
        blog.refresh_from_db()
        self.assertEqual(blog.slug, 'grid-expansion-phase-2')
        form = self.client.get(reverse('superadmin:BlogEdit', args=[blog.id])).content.decode()
        self.assertNotIn('name="slug"', form)

    def test_category_slug_generated(self):
        self.client.post(reverse('superadmin:BlogCategoryAdd'), {'name': 'Press Release', 'name_ar': 'بيان صحفي'})
        self.assertEqual(BlogCategory.objects.get(name='Press Release').slug, 'press-release')

    # ── list filters ──
    def test_blog_status_filter_after_toggle(self):
        a = Blog.objects.create(category=self.news, title='Alpha', title_ar='أ', content='x', content_ar='x', image=make_image())
        b = Blog.objects.create(category=self.news, title='Beta', title_ar='ب', content='x', content_ar='x', image=make_image())
        self.client.post(reverse('superadmin:StatusToggle'), {'model_name': 'Blog', 'id': b.id, 'status': 'false'})

        active = self.client.get(reverse('superadmin:BlogList'), {'status': 'active'}).content.decode()
        inactive = self.client.get(reverse('superadmin:BlogList'), {'status': 'inactive'}).content.decode()
        everything = self.client.get(reverse('superadmin:BlogList'), {'status': 'all'}).content.decode()
        self.assertIn('Alpha', active)
        self.assertNotIn('Beta', active)
        self.assertIn('Beta', inactive)
        self.assertNotIn('Alpha', inactive)
        self.assertIn('Alpha', everything)
        self.assertIn('Beta', everything)
        self.assertIn('id="ajax-list"', active)

    def test_blog_search_and_category_filter(self):
        Blog.objects.create(category=self.news, title='Substation News', title_ar='أ', content='x', content_ar='x', image=make_image())
        article = BlogCategory.objects.get(slug='article')
        Blog.objects.create(category=article, title='Long Read', title_ar='ب', content='x', content_ar='x', image=make_image())
        html = self.client.get(reverse('superadmin:BlogList'), {'category': article.id}).content.decode()
        self.assertIn('Long Read', html)
        self.assertNotIn('Substation News', html)
        html = self.client.get(reverse('superadmin:BlogList'), {'search': 'substation'}).content.decode()
        self.assertIn('Substation News', html)
        self.assertNotIn('Long Read', html)

    def test_category_status_filter(self):
        self.client.post(reverse('superadmin:StatusToggle'), {'model_name': 'BlogCategory', 'id': self.news.id, 'status': 'false'})
        active = self.client.get(reverse('superadmin:BlogCategoryList'), {'status': 'active'}).content.decode()
        inactive = self.client.get(reverse('superadmin:BlogCategoryList'), {'status': 'inactive'}).content.decode()
        self.assertNotIn('>News<', active)
        self.assertIn('>News<', inactive)

    def test_enquiry_filters(self):
        Enquiry.objects.create(source='footer', first_name='Footer Person', email='f@example.com')
        Enquiry.objects.create(source='contact', first_name='Contact Person', email='c@example.com')
        url = reverse('superadmin:EnquiryList')
        html = self.client.get(url, {'source': 'footer'}).content.decode()
        self.assertIn('Footer Person', html)
        self.assertNotIn('Contact Person', html)
        self.assertNotIn('name="read"', html)  # read / unread status removed
        html = self.client.get(url, {'search': 'contact person'}).content.decode()
        self.assertIn('Contact Person', html)
        self.assertNotIn('Footer Person', html)

    def test_career_filters(self):
        common = dict(mobile='1234567', current_location='J', degree='CS', cv=make_pdf())
        CareerApplication.objects.create(first_name='New Guy', email='n@example.com', education='PhD', **common)
        common['cv'] = make_pdf()
        CareerApplication.objects.create(first_name='Hired Gal', email='h@example.com', education='Diploma', status='hired', **common)
        url = reverse('superadmin:CareerApplicationList')
        html = self.client.get(url, {'status': 'hired'}).content.decode()
        self.assertIn('Hired Gal', html)
        self.assertNotIn('New Guy', html)
        html = self.client.get(url, {'education': 'PhD'}).content.decode()
        self.assertIn('New Guy', html)
        self.assertNotIn('Hired Gal', html)

    # ── exports ──
    def test_enquiry_pdf_export_with_arabic(self):
        Enquiry.objects.create(first_name='محمد', last_name='العتيبي', email='m@example.com', message='رسالة تجريبية')
        Enquiry.objects.create(first_name='Sara', last_name='Khan', email='s@example.com', message='Hello')
        res = self.client.get(reverse('superadmin:EnquiryExport'))
        self.assertEqual(res['Content-Type'], 'application/pdf')
        self.assertTrue(res.content.startswith(b'%PDF'))
        self.assertIn('enquiries_', res['Content-Disposition'])

    def test_export_with_no_data_shows_message(self):
        Enquiry.objects.create(source='contact', first_name='A', email='a@example.com')
        res = self.client.get(reverse('superadmin:EnquiryExport'), {'source': 'footer'}, follow=True)
        self.assertEqual(res.redirect_chain[-1][0], reverse('superadmin:EnquiryList') + '?source=footer')
        self.assertContains(res, 'No records found for the selected filters')
        res = self.client.get(reverse('superadmin:CareerApplicationExport'), follow=True)
        self.assertContains(res, 'No records found for the selected filters')

    # ── demo data ──
    def test_seed_demo_data_command_is_idempotent(self):
        from django.core.management import call_command
        out = io.StringIO()
        call_command('seed_demo_data', stdout=out)
        self.assertEqual(Blog.objects.count(), 7)
        self.assertEqual(Blog.objects.filter(is_active=False).count(), 1)
        self.assertEqual(Enquiry.objects.count(), 10)
        self.assertEqual(CareerApplication.objects.count(), 10)
        self.assertTrue(all(b.title_ar and b.content_ar for b in Blog.objects.all()))
        call_command('seed_demo_data', stdout=out)
        self.assertEqual(Blog.objects.count(), 7)
        call_command('seed_demo_data', '--reset', stdout=out)
        self.assertEqual(Enquiry.objects.count(), 10)


@override_settings(MEDIA_ROOT=TEMP_MEDIA, PDF_EXPORT_MAX_ROWS=5)
class ExportLimitTests(TestCase):
    """Large exports: one COUNT decides, PDF is capped, rows stream from the database."""

    def setUp(self):
        User.objects.create_user('admin', 'admin@nit.com', 'StrongPass#2026', is_staff=True)
        self.client.login(username='admin', password='StrongPass#2026')
        Enquiry.objects.bulk_create([Enquiry(first_name=f'P{i}', email=f'p{i}@example.com') for i in range(6)])

    def test_pdf_over_limit_asks_to_narrow_filters(self):
        res = self.client.get(reverse('superadmin:EnquiryExport'), follow=True)
        self.assertContains(res, 'too many for one PDF')
        self.assertContains(res, 'Please narrow the filters')
        self.assertNotContains(res, 'Excel')

    def test_pdf_with_filters_under_limit(self):
        res = self.client.get(reverse('superadmin:EnquiryExport'), {'search': 'P1'})
        self.assertEqual(res['Content-Type'], 'application/pdf')

    def test_pdf_spanning_multiple_table_blocks(self):
        from superadmin import pdf_export
        rows = ((i, f'Name {i}', 'محمد العتيبي') for i in range(pdf_export.ROWS_PER_TABLE * 2 + 7))
        res = pdf_export.pdf_response('t', 'Test', ['#', 'Name', 'AR'], rows, [1, 4, 4], total=507)
        self.assertTrue(res.content.startswith(b'%PDF'))

    def test_dashboard_has_no_export_buttons(self):
        html = self.client.get(reverse('superadmin:Dashboard')).content.decode()
        self.assertNotIn(reverse('superadmin:EnquiryExport'), html)
        self.assertNotIn(reverse('superadmin:CareerApplicationExport'), html)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class LatestAdminChangesTests(TestCase):
    def setUp(self):
        User.objects.create_user('admin', 'admin@nit.com', 'StrongPass#2026', is_staff=True)
        self.client.login(username='admin', password='StrongPass#2026')
        self.news = BlogCategory.objects.get(slug='news')

    def test_blog_detail_page_shows_both_languages(self):
        blog = Blog.objects.create(category=self.news, title='Grid Update', title_ar='تحديث الشبكة',
                                   content='<p>English body</p>', content_ar='<p>محتوى عربي</p>', image=make_image())
        res = self.client.get(reverse('superadmin:BlogDetail', args=[blog.id]))
        self.assertContains(res, 'Grid Update')
        self.assertContains(res, 'تحديث الشبكة')
        self.assertContains(res, '<p>محتوى عربي</p>', html=True)
        self.assertNotContains(res, 'Website page')
        listing = self.client.get(reverse('superadmin:BlogList')).content.decode()
        self.assertIn(f'data-href="{reverse("superadmin:BlogDetail", args=[blog.id])}"', listing)  # whole row opens detail
        self.assertNotIn('fa-eye', listing)

    def test_no_sidebar_counts(self):
        Enquiry.objects.create(first_name='A', email='a@example.com')
        html = self.client.get(reverse('superadmin:Dashboard')).content.decode()
        self.assertNotIn('nav-count', html)

    def test_career_status_pill(self):
        CareerApplication.objects.create(first_name='O', email='o@example.com', mobile='1234567', current_location='J',
                                         education='PhD', degree='CS', status='shortlisted', cv=make_pdf())
        html = self.client.get(reverse('superadmin:CareerApplicationList')).content.decode()
        self.assertIn('application-status-select status-shortlisted', html)

    def test_cors_allows_any_origin(self):
        res = self.client.get('/api/blog-categories/', HTTP_ORIGIN='https://any-site.example')
        self.assertEqual(res['Access-Control-Allow-Origin'], '*')


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ExportPdfOnlyTests(TestCase):
    def setUp(self):
        User.objects.create_user('admin', 'admin@nit.com', 'StrongPass#2026', is_staff=True)
        self.client.login(username='admin', password='StrongPass#2026')

    def test_no_excel_option(self):
        CareerApplication.objects.create(first_name='O', email='o@example.com', mobile='1234567', current_location='J',
                                         education='PhD', degree='CS', cv=make_pdf())
        for url in (reverse('superadmin:EnquiryList'), reverse('superadmin:CareerApplicationList')):
            self.assertNotIn('Excel', self.client.get(url).content.decode())
        res = self.client.get(reverse('superadmin:CareerApplicationExport'), {'type': 'xlsx'})
        self.assertEqual(res['Content-Type'], 'application/pdf')  # ?type is ignored: PDF only

    def test_career_rows_open_detail(self):
        a = CareerApplication.objects.create(first_name='O', email='o@example.com', mobile='1234567', current_location='J',
                                             education='PhD', degree='CS', cv=make_pdf())
        html = self.client.get(reverse('superadmin:CareerApplicationList')).content.decode()
        self.assertIn(f'data-href="{reverse("superadmin:CareerApplicationDetail", args=[a.id])}"', html)
        self.assertNotIn('fa-eye', html)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class PaginationTests(TestCase):
    def setUp(self):
        User.objects.create_user('admin', 'admin@nit.com', 'StrongPass#2026', is_staff=True)
        self.client.login(username='admin', password='StrongPass#2026')
        Enquiry.objects.bulk_create([
            Enquiry(source='footer' if i % 2 else 'contact', first_name=f'Person{i:02d}', email=f'p{i}@example.com')
            for i in range(45)
        ])
        self.url = reverse('superadmin:EnquiryList')

    def page(self, **params):
        return self.client.get(self.url, params).context['enquiries']

    def test_default_page_size_and_custom_sizes(self):
        self.assertEqual(len(self.page().object_list), 20)
        self.assertEqual(len(self.page(per_page=10).object_list), 10)
        self.assertEqual(len(self.page(per_page=50).object_list), 45)
        self.assertEqual(len(self.page(per_page=7).object_list), 20)      # not an allowed size -> default
        self.assertEqual(len(self.page(per_page='abc').object_list), 20)

    def test_out_of_range_page_goes_to_last_page(self):
        self.assertEqual(self.page(page=99).number, 3)
        self.assertEqual(self.page(page='x').number, 1)
        self.assertEqual(self.page(page=99, per_page=10).number, 5)

    def test_bar_shows_count_and_size_even_on_single_page(self):
        html = self.client.get(self.url, {'per_page': 100}).content.decode()
        self.assertIn('of <strong>45</strong> entries', html)
        self.assertIn('per-page-select', html)
        self.assertNotIn('aria-label="Pagination"', html)  # one page -> no page buttons

    def test_page_links_keep_filters_and_size(self):
        html = self.client.get(self.url, {'source': 'contact', 'per_page': 10}).content.decode()
        self.assertIn('?source=contact&amp;per_page=10&amp;page=2', html)
        self.assertIn('title="Last page"', html)
        self.assertIn('page-item disabled', html)  # first/previous disabled on page 1

    def test_delete_returns_to_same_page_and_filters(self):
        target = Enquiry.objects.order_by('-created_at')[25]
        back = f'{self.url}?per_page=10&page=3'
        res = self.client.post(reverse('superadmin:EnquiryDelete', args=[target.id]), {'next': back})
        self.assertRedirects(res, back, fetch_redirect_response=False)

    def test_next_rejects_external_urls(self):
        target = Enquiry.objects.first()
        res = self.client.post(reverse('superadmin:EnquiryDelete', args=[target.id]), {'next': 'https://evil.example/x'})
        self.assertRedirects(res, self.url, fetch_redirect_response=False)
        target = Enquiry.objects.first()
        res = self.client.post(reverse('superadmin:EnquiryDelete', args=[target.id]), {'next': '//evil.example/x'})
        self.assertRedirects(res, self.url, fetch_redirect_response=False)

    def test_blog_save_returns_to_list_position(self):
        news = BlogCategory.objects.get(slug='news')
        blog = Blog.objects.create(category=news, title='Paged', title_ar='صفحة', content='x', content_ar='x', image=make_image())
        back = reverse('superadmin:BlogList') + '?status=all&page=1&per_page=10'
        form = self.client.get(reverse('superadmin:BlogEdit', args=[blog.id]), {'next': back}).content.decode()
        self.assertIn(f'href="{back.replace("&", "&amp;")}"', form)  # Back to List keeps position
        res = self.client.post(reverse('superadmin:BlogEdit', args=[blog.id]), {
            'title': 'Paged', 'title_ar': 'صفحة', 'category': news.id, 'content': '<p>x</p>', 'content_ar': '<p>x</p>',
            'date': '2026-01-01', 'next': back,
        })
        self.assertRedirects(res, back, fetch_redirect_response=False)

    def test_all_lists_paginate(self):
        for name in ('BlogCategoryList', 'BlogList', 'EnquiryList', 'CareerApplicationList'):
            res = self.client.get(reverse(f'superadmin:{name}'), {'status': 'all'})
            self.assertEqual(res.status_code, 200, name)
