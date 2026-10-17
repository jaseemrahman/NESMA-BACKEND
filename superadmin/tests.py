from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

class ProfileViewTestCase(TestCase):
    def setUp(self):
        # Create a test superuser
        self.username = 'admin'
        self.password = 'super_secure_pass_123'
        self.email = 'admin@test.com'
        self.user = User.objects.create_superuser(
            username=self.username,
            email=self.email,
            password=self.password
        )
        self.client = Client()

    def test_profile_view_get_requires_login(self):
        response = self.client.get(reverse('superadmin:Profile'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('superadmin:login'), response.url)

    def test_profile_view_get_logged_in(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('superadmin:Profile'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'superadmin/layout/profile.html')

    def test_profile_view_post_success(self):
        self.client.force_login(self.user)
        new_password = 'new_awesome_password_987'
        response = self.client.post(reverse('superadmin:Profile'), {
            'oldpassword': self.password,
            'newpassword': new_password,
            'conpassword': new_password,
        })
        # Check redirect to Dashboard
        self.assertRedirects(response, reverse('superadmin:Dashboard'))
        
        # Check user can authenticate with the new password
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))

    def test_profile_view_post_incorrect_current_password(self):
        self.client.force_login(self.user)
        new_password = 'new_awesome_password_987'
        response = self.client.post(reverse('superadmin:Profile'), {
            'oldpassword': 'wrong_old_password',
            'newpassword': new_password,
            'conpassword': new_password,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'superadmin/layout/profile.html')
        
        # Check user password did not change
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))

    def test_profile_view_post_mismatch_new_passwords(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('superadmin:Profile'), {
            'oldpassword': self.password,
            'newpassword': 'new_awesome_password_1',
            'conpassword': 'new_awesome_password_2',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'superadmin/layout/profile.html')
        
        # Check password didn't change
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))

    def test_profile_view_post_short_new_password(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('superadmin:Profile'), {
            'oldpassword': self.password,
            'newpassword': 'short',
            'conpassword': 'short',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'superadmin/layout/profile.html')
        
        # Check password didn't change
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))


from superadmin.models import Blog, BlogCategory


class CategoryValidationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='admin_cat',
            email='admin_cat@test.com',
            password='password123'
        )
        self.client.force_login(self.user)

    def test_blog_category_duplicate_name_validation(self):
        response = self.client.post(reverse('superadmin:BlogCategoryAdd'), {'name': 'NEWS'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(BlogCategory.objects.filter(name__iexact='news').count(), 1)

    def test_blog_category_saves_arabic_name(self):
        self.client.post(reverse('superadmin:BlogCategoryAdd'), {'name': 'Press Release', 'name_ar': 'بيان صحفي'})
        category = BlogCategory.objects.get(name='Press Release')
        self.assertEqual((category.name_ar, category.slug), ('بيان صحفي', 'press-release'))

    def test_blog_add_mandatory_category_validation(self):
        response = self.client.post(reverse('superadmin:BlogAdd'), {
            'title': 'Test Blog',
            'content': '<p>Body</p>',
            'category': '',  # missing category
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Blog.objects.count(), 0)
