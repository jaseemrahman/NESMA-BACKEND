"""
Fill every admin module with realistic demo data (English + Arabic).

    python manage.py seed_demo_data            # add demo data (skips records that already exist)
    python manage.py seed_demo_data --reset    # delete previous demo data first, then re-create it

Demo enquiries / applications use @example.com emails so they are easy to identify and remove.
"""
import io
from datetime import timedelta
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from superadmin.models import Blog, BlogCategory, CareerApplication, Enquiry

DEMO_MEDIA = Path(__file__).resolve().parent / 'demo_media'
DEMO_EMAIL_DOMAIN = '@example.com'

BLOGS = [
    {
        'category': 'news', 'image': 's-1.jpg', 'days_ago': 10,
        'title': 'Nesma Infrastructure & Technology Signs a Contract Valued at Over SAR 160 Million',
        'title_ar': 'نسما للبنية التحتية والتقنية توقع عقداً بقيمة تتجاوز 160 مليون ريال',
        'location': 'Riyadh, Saudi Arabia', 'location_ar': 'الرياض، المملكة العربية السعودية',
        'short_description': 'A new contract that reinforces NIT as a trusted delivery partner for critical infrastructure.',
        'short_description_ar': 'عقد جديد يعزز مكانة نسما كشريك موثوق لتنفيذ مشاريع البنية التحتية الحيوية.',
        'content': '<p>We are proud to announce that <strong>Nesma Infrastructure &amp; Technology</strong> has signed a new '
                   'contract valued at over SAR 160 million, reinforcing our position as a trusted delivery partner for '
                   'critical infrastructure across the Kingdom.</p><p>The scope covers design, procurement and construction '
                   'work that will expand regional power transmission capacity.</p>',
        'content_ar': '<p>يسرنا الإعلان عن توقيع <strong>نسما للبنية التحتية والتقنية</strong> عقداً جديداً بقيمة تتجاوز '
                      '160 مليون ريال، مما يعزز مكانتنا كشريك موثوق لتنفيذ مشاريع البنية التحتية الحيوية في المملكة.</p>'
                      '<p>يشمل نطاق العمل التصميم والتوريد والإنشاء لتوسيع قدرة نقل الطاقة الإقليمية.</p>',
    },
    {
        'category': 'announcement', 'image': 's-2.jpg', 'days_ago': 22,
        'title': 'NIT Signs New Contract with the SEC in Jubail, Valued at Over SAR 500 Million',
        'title_ar': 'نسما توقع عقداً جديداً مع الشركة السعودية للكهرباء في الجبيل بقيمة تتجاوز 500 مليون ريال',
        'location': 'Jubail, Saudi Arabia', 'location_ar': 'الجبيل، المملكة العربية السعودية',
        'short_description': 'A major substation and transmission package for the Saudi Electricity Company.',
        'short_description_ar': 'حزمة رئيسية لمحطات التحويل وخطوط النقل للشركة السعودية للكهرباء.',
        'content': '<p>NIT has been awarded a contract by the Saudi Electricity Company in Jubail valued at over SAR 500 '
                   'million, covering new substations and high-voltage transmission lines.</p>',
        'content_ar': '<p>حصلت نسما على عقد من الشركة السعودية للكهرباء في الجبيل بقيمة تتجاوز 500 مليون ريال، '
                      'يشمل محطات تحويل جديدة وخطوط نقل جهد عالٍ.</p>',
    },
    {
        'category': 'insights', 'image': 's3.jpg', 'days_ago': 35,
        'title': 'NIT Signs New Contract with the Saudi Electricity Company',
        'title_ar': 'نسما توقع عقداً جديداً مع الشركة السعودية للكهرباء',
        'location': 'Riyadh, Saudi Arabia', 'location_ar': 'الرياض، المملكة العربية السعودية',
        'short_description': 'Strengthening grid reliability with a new distribution upgrade programme.',
        'short_description_ar': 'تعزيز موثوقية الشبكة من خلال برنامج جديد لتطوير شبكات التوزيع.',
        'content': '<p>The new agreement with the Saudi Electricity Company focuses on distribution network upgrades that '
                   'improve reliability for residential and industrial customers.</p>',
        'content_ar': '<p>تركز الاتفاقية الجديدة مع الشركة السعودية للكهرباء على تطوير شبكات التوزيع لتحسين '
                      'موثوقية الخدمة للعملاء السكنيين والصناعيين.</p>',
    },
    {
        'category': 'news', 'image': 'b3.jpg', 'days_ago': 48,
        'title': 'New Contract with the National Grid SA',
        'title_ar': 'عقد جديد مع الشبكة الوطنية السعودية',
        'location': 'Riyadh, Saudi Arabia', 'location_ar': 'الرياض، المملكة العربية السعودية',
        'short_description': 'Supporting the National Grid SA with transmission and smart-grid capabilities.',
        'short_description_ar': 'دعم الشبكة الوطنية السعودية بقدرات النقل والشبكات الذكية.',
        'content': '<p>NIT will deliver transmission infrastructure and smart-grid integration for the National Grid SA, '
                   'supporting the Kingdom\'s energy transition goals.</p>',
        'content_ar': '<p>ستنفذ نسما بنية تحتية للنقل وتكاملاً للشبكات الذكية لصالح الشبكة الوطنية السعودية، '
                      'دعماً لأهداف تحول الطاقة في المملكة.</p>',
    },
    {
        'category': 'announcement', 'image': 'blog2.jpg', 'days_ago': 63,
        'title': 'The China-Saudi Economic Cooperation Forum 2026',
        'title_ar': 'منتدى التعاون الاقتصادي السعودي الصيني 2026',
        'location': 'Riyadh, Saudi Arabia', 'location_ar': 'الرياض، المملكة العربية السعودية',
        'short_description': 'NIT joined industry leaders to discuss infrastructure and technology partnerships.',
        'short_description_ar': 'شاركت نسما قادة القطاع في مناقشة شراكات البنية التحتية والتقنية.',
        'content': '<p>NIT participated in the China-Saudi Economic Cooperation Forum 2026, exploring partnerships in '
                   'energy, digital infrastructure and advanced manufacturing.</p>',
        'content_ar': '<p>شاركت نسما في منتدى التعاون الاقتصادي السعودي الصيني 2026، لاستكشاف الشراكات في مجالات '
                      'الطاقة والبنية التحتية الرقمية والتصنيع المتقدم.</p>',
    },
    {
        'category': 'article', 'image': 'blog3.jpg', 'days_ago': 80,
        'title': 'The International Alignment Forum on Saudi Vision 2030',
        'title_ar': 'المنتدى الدولي للمواءمة مع رؤية السعودية 2030',
        'location': 'Riyadh, Saudi Arabia', 'location_ar': 'الرياض، المملكة العربية السعودية',
        'short_description': 'How local content and digital transformation shape the next decade of infrastructure.',
        'short_description_ar': 'كيف يشكل المحتوى المحلي والتحول الرقمي العقد القادم من البنية التحتية.',
        'content': '<p>At the International Alignment Forum on Saudi Vision 2030, NIT shared its roadmap to reach 50% '
                   'local content by 2027 while accelerating digital transformation.</p>',
        'content_ar': '<p>في المنتدى الدولي للمواءمة مع رؤية السعودية 2030، استعرضت نسما خارطة طريقها للوصول إلى '
                      '50% من المحتوى المحلي بحلول 2027 مع تسريع التحول الرقمي.</p>',
    },
    {
        # inactive draft: useful for testing the Active / Inactive filters
        'category': 'news', 'image': 's-1.jpg', 'days_ago': 2, 'is_active': False,
        'title': 'Draft: Oxagon Village Project Update',
        'title_ar': 'مسودة: تحديث مشروع قرية أوكساجون',
        'location': 'NEOM, Saudi Arabia', 'location_ar': 'نيوم، المملكة العربية السعودية',
        'short_description': 'Unpublished draft - not visible on the website.',
        'short_description_ar': 'مسودة غير منشورة - لا تظهر على الموقع.',
        'content': '<p>Progress update on the Oxagon Village living community (draft).</p>',
        'content_ar': '<p>تحديث حول تقدم مجتمع قرية أوكساجون السكني (مسودة).</p>',
    },
]

ENQUIRIES = [
    # (source, first, last, company, phone, local email, message, language, hours_ago)
    ('contact', 'Sara', 'Khan', 'ACME Holdings', '+966 55 063 4599', 'sara.khan',
     'We need a quote for a 132kV substation project in Dammam.', 'en', 3),
    ('footer', 'Ahmed Al-Harbi', '', '', '', 'ahmed.harbi',
     'I would like to know more about investment opportunities with NIT.', 'en', 9),
    ('contact', 'محمد', 'العتيبي', 'شركة الأفق للمقاولات', '+966 50 123 4567', 'm.otaibi',
     'نرغب في مناقشة شراكة لتنفيذ مشروع شبكة توزيع في جدة.', 'ar', 20),
    ('footer', 'نورة القحطاني', '', '', '', 'noura.q',
     'أرغب في معرفة المزيد عن حلول التحول الرقمي لديكم.', 'ar', 30),
    ('contact', 'James', 'Walker', 'Gulf Energy Partners', '+44 20 7946 0958', 'james.walker',
     'Interested in partnering on renewable energy EPC projects in the Kingdom.', 'en', 52),
    ('contact', 'Fatima', 'Zahra', 'Smart Cities Co.', '+966 56 789 0123', 'fatima.zahra',
     'Please share your capability statement for smart-city infrastructure.', 'en', 75),
    ('footer', 'Omar Siddiqui', '', '', '', 'omar.s',
     'Do you provide operations and maintenance services for industrial plants?', 'en', 100),
    ('contact', 'خالد', 'الشمري', 'مجموعة الريادة', '+966 55 987 6543', 'khalid.shammari',
     'نود الاستفسار عن خدمات الأمن السيبراني للبنية التحتية الحيوية.', 'ar', 130),
    ('footer', 'Priya Nair', '', '', '', 'priya.nair',
     'Looking for vendor registration details for upcoming tenders.', 'en', 170),
    ('contact', 'David', 'Chen', 'Orient Technologies', '+86 10 5555 0199', 'david.chen',
     'We are a fibre-optics manufacturer and would like to become a supplier.', 'en', 210),
]

APPLICATIONS = [
    # (first, last, local email, mobile, location, nationality, education, degree, status, language, days_ago)
    ('Omar', 'Hassan', 'omar.hassan', '+966 55 000 1111', 'Jeddah', 'Saudi Arabian', "Bachelor's Degree",
     'Electrical Engineering', 'new', 'en', 0),
    ('ريم', 'الدوسري', 'reem.d', '+966 50 222 3333', 'الرياض', 'Saudi Arabian', "Master's Degree",
     'هندسة الطاقة المتجددة', 'new', 'ar', 1),
    ('Arjun', 'Menon', 'arjun.menon', '+966 56 444 5555', 'Dammam', 'Indian', "Bachelor's Degree",
     'Civil Engineering', 'reviewed', 'en', 3),
    ('Layla', 'Haddad', 'layla.haddad', '+966 54 666 7777', 'Riyadh', 'Lebanese', "Master's Degree",
     'Project Management', 'shortlisted', 'en', 6),
    ('Mohammed', 'Farouk', 'm.farouk', '+966 53 888 9999', 'Jeddah', 'Egyptian', 'Diploma',
     'Electrical Technology', 'rejected', 'en', 9),
    ('عبدالله', 'الزهراني', 'abdullah.z', '+966 59 123 0000', 'جدة', 'Saudi Arabian', 'PhD',
     'أنظمة الطاقة الكهربائية', 'hired', 'ar', 14),
    ('Maria', 'Santos', 'maria.santos', '+966 58 321 6540', 'Al Khobar', 'Filipino', "Bachelor's Degree",
     'Computer Science', 'new', 'en', 18),
    ('Yousef', 'Khalil', 'yousef.khalil', '+966 57 654 3210', 'Riyadh', 'Jordanian', "Master's Degree",
     'Cybersecurity', 'reviewed', 'en', 25),
    ('Ali', 'Raza', 'ali.raza', '+966 55 789 4561', 'Jubail', 'Pakistani', 'High School',
     'Technical Certificate', 'new', 'en', 33),
    ('Sophie', 'Turner', 'sophie.turner', '+966 50 147 2583', 'NEOM', 'British', "Bachelor's Degree",
     'Mechanical Engineering', 'shortlisted', 'en', 41),
]


def make_cv_pdf(name, degree, email):
    """A small one-page CV so the demo 'View / Download CV' buttons work."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle(f'CV - {name}')
    pdf.setFont('Helvetica-Bold', 20)
    pdf.drawString(60, 780, 'Curriculum Vitae')
    pdf.setFont('Helvetica', 12)
    pdf.drawString(60, 750, f'Candidate ID: {email.split("@")[0]}')
    pdf.drawString(60, 730, f'Email: {email}')
    pdf.drawString(60, 710, 'Field: Engineering & Technology')
    pdf.drawString(60, 680, 'Demo CV generated by "manage.py seed_demo_data".')
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


class Command(BaseCommand):
    help = 'Create demo blogs (EN/AR), enquiries and career applications for testing the admin panel and API.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Delete existing demo data before seeding.')

    @transaction.atomic
    def handle(self, *args, **options):
        if options['reset']:
            self.reset()
        blogs = self.seed_blogs()
        enquiries = self.seed_enquiries()
        applications = self.seed_applications()
        self.stdout.write(self.style.SUCCESS(
            f'Demo data ready: {blogs} blogs, {enquiries} enquiries, {applications} career applications created.'
        ))

    def reset(self):
        titles = [b['title'] for b in BLOGS]
        for blog in Blog.objects.filter(title__in=titles):
            blog.delete()  # signal removes the image file
        Enquiry.objects.filter(email__endswith=DEMO_EMAIL_DOMAIN).delete()
        for application in CareerApplication.objects.filter(email__endswith=DEMO_EMAIL_DOMAIN):
            application.cv.delete(save=False)
            application.delete()
        self.stdout.write('Previous demo data removed.')

    def seed_blogs(self):
        categories = {c.slug: c for c in BlogCategory.objects.all()}
        today = timezone.localdate()
        created = 0
        for sequence, data in enumerate(BLOGS, start=1):
            if Blog.objects.filter(title=data['title']).exists():
                continue
            fields = {k: v for k, v in data.items() if k not in ('category', 'image', 'days_ago')}
            blog = Blog(category=categories[data['category']], date=today - timedelta(days=data['days_ago']),
                        sequence=sequence, **fields)
            image_path = DEMO_MEDIA / data['image']
            blog.image = SimpleUploadedFile(image_path.name, image_path.read_bytes(), content_type='image/jpeg')
            blog.save()
            created += 1
        return created

    def seed_enquiries(self):
        now = timezone.now()
        created = 0
        for source, first, last, company, phone, local, message, lang, hours in ENQUIRIES:
            email = local + DEMO_EMAIL_DOMAIN
            if Enquiry.objects.filter(email=email).exists():
                continue
            enquiry = Enquiry.objects.create(
                source=source, first_name=first, last_name=last, company_name=company, phone=phone,
                email=email, message=message, language=lang, ip_address='127.0.0.1',
            )
            Enquiry.objects.filter(pk=enquiry.pk).update(created_at=now - timedelta(hours=hours))
            created += 1
        return created

    def seed_applications(self):
        now = timezone.now()
        created = 0
        for first, last, local, mobile, location, nationality, education, degree, status, lang, days in APPLICATIONS:
            email = local + DEMO_EMAIL_DOMAIN
            if CareerApplication.objects.filter(email=email).exists():
                continue
            application = CareerApplication(
                first_name=first, last_name=last, email=email, mobile=mobile, current_location=location,
                nationality=nationality, education=education, degree=degree, status=status, language=lang,
                ip_address='127.0.0.1',
            )
            application.cv.save(f'{local}.pdf', ContentFile(make_cv_pdf(f'{first} {last}', degree, email)), save=False)
            application.save()
            CareerApplication.objects.filter(pk=application.pk).update(created_at=now - timedelta(days=days, hours=2))
            created += 1
        return created
