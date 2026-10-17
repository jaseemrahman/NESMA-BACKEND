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
        self.assertEqual(res['Access-Control-Allow-Origin'], 'https://nit-hazel.vercel.app')


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
        self.assertTrue(Enquiry.objects.filter(pk=enquiry.pk, is_read=False).exists())

    def test_create_blog_from_admin(self):
        res = self.client.post(reverse('superadmin:BlogAdd'), {
            'title': 'New Substation Project', 'title_ar': 'مشروع محطة جديدة', 'category': self.news.id,
            'content': '<p>Body</p>', 'date': '2026-03-12', 'image': make_image(),
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
            'title': 'Same Title', 'category': self.news.id, 'content': '<p>Body</p>',
            'date': '2026-03-12', 'image': make_image(),
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Blog.objects.count(), 1)
        self.assertContains(res, 'already used by another blog')

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

    def test_mark_enquiry_read(self):
        enquiry = Enquiry.objects.create(first_name='A', email='a@b.com')
        self.client.post(reverse('superadmin:EnquiryMarkRead', args=[enquiry.id]), {'is_read': 'true'})
        enquiry.refresh_from_db()
        self.assertTrue(enquiry.is_read)

    def test_login_required(self):
        self.client.logout()
        res = self.client.get(reverse('superadmin:EnquiryList'))
        self.assertEqual(res.status_code, 302)
