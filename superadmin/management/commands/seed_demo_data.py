"""
Fill every admin module with realistic demo data (English + Arabic).

    python manage.py seed_demo_data               # blogs + demo enquiries/applications (skips existing records)
    python manage.py seed_demo_data --blogs-only  # only the website's media-centre posts (use on servers)
    python manage.py seed_demo_data --reset       # delete previous demo data first, then re-create it

Demo enquiries / applications use @example.com emails so they are easy to identify and remove.
"""
import datetime
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

# The six posts published on https://nit-hazel.vercel.app/media (same slugs as the website URLs)
BLOGS = [
    {
        'slug': 'sar-160-million-contract', 'category': 'news', 'image': 's-1.jpg', 'date': '2026-03-12',
        'title': 'Nesma Infrastructure & Technology Signs a Contract Valued at Over SAR 160 Million',
        'title_ar': 'نسما للبنية التحتية والتقنية توقّع عقداً بقيمة تتجاوز 160 مليون ريال',
        'location': 'Riyadh, Saudi Arabia', 'location_ar': 'الرياض، المملكة العربية السعودية',
        'short_description': 'A new contract valued at over SAR 160 million reinforces NIT as a trusted delivery partner '
                             'for critical infrastructure across the Kingdom.',
        'short_description_ar': 'عقد جديد بقيمة تتجاوز 160 مليون ريال يعزز مكانة نسما كشريك موثوق لتنفيذ مشاريع البنية '
                                'التحتية الحيوية في المملكة.',
        'content': '<p>We are proud to announce that <strong>Nesma Infrastructure &amp; Technology</strong> has signed a new '
                   'contract valued at over SAR 160 million, reinforcing our position as a trusted delivery partner for '
                   'critical infrastructure across the Kingdom.</p>'
                   '<p>The scope covers design, procurement, and construction work that will expand regional power '
                   'transmission capacity, supporting growing demand across commercial and industrial sectors.</p>'
                   '<p>At NIT, we remain committed to delivering projects that strengthen the Kingdom\'s infrastructure '
                   'backbone while upholding the highest standards of safety, quality, and execution.</p>',
        'content_ar': '<p>يسرّنا الإعلان عن توقيع <strong>نسما للبنية التحتية والتقنية</strong> عقداً جديداً بقيمة تتجاوز '
                      '160 مليون ريال، مما يعزز مكانتنا كشريك موثوق لتنفيذ مشاريع البنية التحتية الحيوية في المملكة.</p>'
                      '<p>يشمل نطاق العمل أعمال التصميم والتوريد والإنشاء لتوسيع قدرة نقل الطاقة الإقليمية، دعماً للطلب '
                      'المتزايد في القطاعات التجارية والصناعية.</p>'
                      '<p>نلتزم في نسما بتنفيذ مشاريع تعزز البنية التحتية للمملكة مع الحفاظ على أعلى معايير السلامة '
                      'والجودة والتنفيذ.</p>',
    },
    {
        'slug': 'sec-jubail-contract', 'category': 'announcement', 'image': 's-2.jpg', 'date': '2026-02-28',
        'title': 'Nesma Infrastructure & Technology Signs New Contract with the SEC in Jubail, valued at over SAR 500 Million',
        'title_ar': 'نسما للبنية التحتية والتقنية توقّع عقداً جديداً مع الشركة السعودية للكهرباء في الجبيل بقيمة تتجاوز 500 مليون ريال',
        'location': 'Riyadh, Saudi Arabia', 'location_ar': 'الرياض، المملكة العربية السعودية',
        'short_description': 'A new SAR 500 million contract with the Saudi Electricity Company expands NIT\'s footprint '
                             'in the Eastern Province.',
        'short_description_ar': 'عقد جديد بقيمة 500 مليون ريال مع الشركة السعودية للكهرباء يوسّع حضور نسما في المنطقة الشرقية.',
        'content': '<p><strong>Nesma Infrastructure &amp; Technology</strong> has signed a new contract with the Saudi '
                   'Electricity Company (SEC) in Jubail, valued at over SAR 500 million, further expanding our footprint '
                   'in the Eastern Province.</p>'
                   '<p>The project will deliver new substation and transmission infrastructure designed to support the '
                   'region\'s industrial growth and long-term energy security.</p>'
                   '<p>This award reflects the continued confidence our partners place in NIT\'s ability to deliver complex '
                   'energy infrastructure on time and to the highest technical standards.</p>',
        'content_ar': '<p>وقّعت <strong>نسما للبنية التحتية والتقنية</strong> عقداً جديداً مع الشركة السعودية للكهرباء في '
                      'الجبيل بقيمة تتجاوز 500 مليون ريال، مما يوسّع حضورنا في المنطقة الشرقية.</p>'
                      '<p>سيوفر المشروع محطات تحويل وبنية تحتية جديدة لنقل الطاقة لدعم النمو الصناعي في المنطقة وتعزيز '
                      'أمن الطاقة على المدى الطويل.</p>'
                      '<p>تعكس هذه الترسية الثقة المستمرة التي يوليها شركاؤنا لقدرة نسما على تنفيذ مشاريع الطاقة المعقدة '
                      'في الوقت المحدد ووفق أعلى المعايير الفنية.</p>',
    },
    {
        'slug': 'saudi-electricity-company-contract', 'category': 'insights', 'image': 's3.jpg', 'date': '2026-01-15',
        'title': 'Nesma Infrastructure & Technology Signs New Contract with the Saudi Electricity Company',
        'title_ar': 'نسما للبنية التحتية والتقنية توقّع عقداً جديداً مع الشركة السعودية للكهرباء',
        'location': 'Riyadh, Saudi Arabia', 'location_ar': 'الرياض، المملكة العربية السعودية',
        'short_description': 'Extending a long-standing partnership to deliver national power infrastructure across '
                             'multiple substation sites.',
        'short_description_ar': 'امتداد لشراكة طويلة لتنفيذ البنية التحتية الوطنية للطاقة في عدة مواقع لمحطات التحويل.',
        'content': '<p><strong>Nesma Infrastructure &amp; Technology</strong> has signed a new contract with the Saudi '
                   'Electricity Company, extending our long-standing partnership in delivering national power '
                   'infrastructure.</p>'
                   '<p>The agreement covers engineering, procurement, and construction services across multiple substation '
                   'sites, reinforcing grid reliability for communities and industry alike.</p>'
                   '<p>We look forward to building on this partnership as the Kingdom continues to scale its energy '
                   'infrastructure in line with Vision 2030.</p>',
        'content_ar': '<p>وقّعت <strong>نسما للبنية التحتية والتقنية</strong> عقداً جديداً مع الشركة السعودية للكهرباء، '
                      'امتداداً لشراكتنا الطويلة في تنفيذ البنية التحتية الوطنية للطاقة.</p>'
                      '<p>تشمل الاتفاقية خدمات الهندسة والتوريد والإنشاء في عدة مواقع لمحطات التحويل، مما يعزز موثوقية '
                      'الشبكة للمجتمعات والقطاع الصناعي على حد سواء.</p>'
                      '<p>نتطلع إلى البناء على هذه الشراكة مع مواصلة المملكة توسيع بنيتها التحتية للطاقة تماشياً مع '
                      'رؤية 2030.</p>',
    },
    {
        'slug': 'national-grid-sa-contract', 'category': 'news', 'image': 'b3.jpg', 'date': '2026-03-12',
        'title': 'New contract with the National Grid SA',
        'title_ar': 'عقد جديد مع الشبكة الوطنية السعودية',
        'location': 'Riyadh, Saudi Arabia', 'location_ar': 'الرياض، المملكة العربية السعودية',
        'short_description': 'Critical upgrades to transmission infrastructure that improve grid resilience and capacity.',
        'short_description_ar': 'تطويرات حيوية للبنية التحتية لنقل الطاقة تعزز مرونة الشبكة وقدرتها.',
        'content': '<p><strong>Nesma Infrastructure &amp; Technology</strong> has been awarded a new contract with the '
                   'National Grid SA, covering critical upgrades to transmission infrastructure across the network.</p>'
                   '<p>The work will improve grid resilience and capacity, supporting the Kingdom\'s growing energy demand '
                   'across residential, commercial, and industrial sectors.</p>'
                   '<p>This award builds on NIT\'s track record of delivering large-scale energy infrastructure projects '
                   'safely, efficiently, and to the highest quality standards.</p>',
        'content_ar': '<p>حصلت <strong>نسما للبنية التحتية والتقنية</strong> على عقد جديد مع الشبكة الوطنية السعودية يشمل '
                      'تطويرات حيوية للبنية التحتية لنقل الطاقة في أنحاء الشبكة.</p>'
                      '<p>ستعزز الأعمال مرونة الشبكة وقدرتها، دعماً للطلب المتزايد على الطاقة في المملكة في القطاعات '
                      'السكنية والتجارية والصناعية.</p>'
                      '<p>تأتي هذه الترسية امتداداً لسجل نسما في تنفيذ مشاريع الطاقة الكبرى بأمان وكفاءة ووفق أعلى '
                      'معايير الجودة.</p>',
    },
    {
        'slug': 'china-saudi-economic-cooperation-forum-2026', 'category': 'announcement', 'image': 'blog2.jpg',
        'date': '2026-02-28',
        'title': 'The China–Saudi Economic Cooperation Forum 2026',
        'title_ar': 'منتدى التعاون الاقتصادي الصيني السعودي 2026',
        'location': 'Riyadh, Saudi Arabia', 'location_ar': 'الرياض، المملكة العربية السعودية',
        'short_description': 'NIT joined industry and government leaders to explore bilateral investment and technology '
                             'exchange.',
        'short_description_ar': 'شاركت نسما قادة القطاع والحكومة في استكشاف فرص الاستثمار الثنائي وتبادل التقنية.',
        'content': '<p><strong>Nesma Infrastructure &amp; Technology</strong> participated in the China–Saudi Economic '
                   'Cooperation Forum 2026, joining industry and government leaders to explore new avenues for bilateral '
                   'investment and technology exchange.</p>'
                   '<p>Discussions centered on infrastructure, energy, and digital transformation — sectors where NIT '
                   'continues to play an active role in delivering the Kingdom\'s national priorities.</p>'
                   '<p>We remain committed to building strategic partnerships that bring world-class technology and '
                   'expertise to Saudi Arabia\'s infrastructure sector.</p>',
        'content_ar': '<p>شاركت <strong>نسما للبنية التحتية والتقنية</strong> في منتدى التعاون الاقتصادي الصيني السعودي '
                      '2026، إلى جانب قادة القطاع والحكومة لاستكشاف آفاق جديدة للاستثمار الثنائي وتبادل التقنية.</p>'
                      '<p>تمحورت النقاشات حول البنية التحتية والطاقة والتحول الرقمي، وهي قطاعات تواصل نسما فيها دورها '
                      'الفاعل في تحقيق الأولويات الوطنية للمملكة.</p>'
                      '<p>نلتزم ببناء شراكات استراتيجية تجلب التقنية والخبرات العالمية إلى قطاع البنية التحتية في '
                      'المملكة العربية السعودية.</p>',
    },
    {
        'slug': 'international-alignment-forum-vision-2030', 'category': 'insights', 'image': 'blog3.jpg',
        'date': '2026-01-15',
        'title': 'The International Alignment Forum on Saudi Vision 2030',
        'title_ar': 'المنتدى الدولي للمواءمة مع رؤية السعودية 2030',
        'location': 'Riyadh, Saudi Arabia', 'location_ar': 'الرياض، المملكة العربية السعودية',
        'short_description': 'A keynote on turning ambitious visions into tangible achievements through execution and '
                             'strategic partnerships.',
        'short_description_ar': 'كلمة رئيسية حول تحويل الرؤى الطموحة إلى إنجازات ملموسة من خلال التنفيذ والشراكات الاستراتيجية.',
        'content': '<p>We are proud at <strong>Nesma Infrastructure &amp; Technology</strong> to have participated in the '
                   'International Alignment Forum on Saudi Vision 2030, where Eng. <strong>Rayan Alamoudi</strong>, '
                   'Executive Manager of Strategy &amp; Business Development, delivered a keynote speech on transforming '
                   'ambitious visions into tangible achievements through execution and strategic partnerships.</p>'
                   '<p>Saudi Arabia\'s Vision 2030 is not merely a strategic direction — it is a national transformation '
                   'program driven by technology, investment, and innovation. Through key sectors such as smart cities, '
                   'energy sustainability, advanced manufacturing, and the digital economy, the Kingdom is actively '
                   'building a competitive and sustainable future.</p>'
                   '<p>At NIT, we remain committed to supporting this transformation through resilient infrastructure, '
                   'advanced technological solutions, and long-term partnerships that create real impact on the ground.</p>',
        'content_ar': '<p>نفخر في <strong>نسما للبنية التحتية والتقنية</strong> بمشاركتنا في المنتدى الدولي للمواءمة مع '
                      'رؤية السعودية 2030، حيث ألقى المهندس <strong>ريان العمودي</strong>، المدير التنفيذي للاستراتيجية '
                      'وتطوير الأعمال، كلمة رئيسية حول تحويل الرؤى الطموحة إلى إنجازات ملموسة من خلال التنفيذ '
                      'والشراكات الاستراتيجية.</p>'
                      '<p>رؤية السعودية 2030 ليست مجرد توجه استراتيجي، بل برنامج تحول وطني تقوده التقنية والاستثمار '
                      'والابتكار. ومن خلال قطاعات رئيسية مثل المدن الذكية واستدامة الطاقة والتصنيع المتقدم والاقتصاد '
                      'الرقمي، تبني المملكة مستقبلاً تنافسياً ومستداماً.</p>'
                      '<p>نلتزم في نسما بدعم هذا التحول من خلال بنية تحتية مرنة وحلول تقنية متقدمة وشراكات طويلة الأمد '
                      'تحقق أثراً حقيقياً على أرض الواقع.</p>',
    },
]

# Extra unpublished draft (full demo only) for testing the Active / Inactive filters
DRAFT_BLOG = {
    'slug': 'oxagon-village-project-update', 'category': 'news', 'image': 's-1.jpg', 'date': None, 'is_active': False,
    'title': 'Draft: Oxagon Village Project Update',
    'title_ar': 'مسودة: تحديث مشروع قرية أوكساجون',
    'location': 'NEOM, Saudi Arabia', 'location_ar': 'نيوم، المملكة العربية السعودية',
    'short_description': 'Unpublished draft - not visible on the website.',
    'short_description_ar': 'مسودة غير منشورة - لا تظهر على الموقع.',
    'content': '<p>Progress update on the Oxagon Village living community (draft).</p>',
    'content_ar': '<p>تحديث حول تقدم مجتمع قرية أوكساجون السكني (مسودة).</p>',
}

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
        parser.add_argument('--blogs-only', action='store_true',
                            help='Only add blog categories + the published website posts (no enquiries/applications/draft).')

    @transaction.atomic
    def handle(self, *args, **options):
        blogs_only = options['blogs_only']
        if options['reset']:
            self.reset(blogs_only)
        # make sure the website's categories exist and are published
        BlogCategory.objects.filter(slug__in={b['category'] for b in BLOGS}).update(is_active=True)
        blogs = self.seed_blogs(BLOGS if blogs_only else BLOGS + [DRAFT_BLOG])
        if blogs_only:
            self.stdout.write(self.style.SUCCESS(f'Website media posts ready: {blogs} blogs created.'))
            return
        enquiries = self.seed_enquiries()
        applications = self.seed_applications()
        self.stdout.write(self.style.SUCCESS(
            f'Demo data ready: {blogs} blogs, {enquiries} enquiries, {applications} career applications created.'
        ))

    def reset(self, blogs_only=False):
        for blog in Blog.objects.filter(slug__in=[b['slug'] for b in BLOGS + [DRAFT_BLOG]]):
            blog.delete()  # signal removes the image + thumbnail files
        if blogs_only:
            self.stdout.write('Previous demo blogs removed.')
            return
        Enquiry.objects.filter(email__endswith=DEMO_EMAIL_DOMAIN).delete()
        for application in CareerApplication.objects.filter(email__endswith=DEMO_EMAIL_DOMAIN):
            application.cv.delete(save=False)
            application.delete()
        self.stdout.write('Previous demo data removed.')

    def seed_blogs(self, posts):
        categories = {c.slug: c for c in BlogCategory.objects.all()}
        created = 0
        for sequence, data in enumerate(posts, start=1):
            if Blog.objects.filter(slug=data['slug']).exists():
                continue
            fields = {k: v for k, v in data.items() if k not in ('category', 'image', 'date')}
            date = datetime.date.fromisoformat(data['date']) if data['date'] else timezone.localdate()
            blog = Blog(category=categories[data['category']], date=date, sequence=sequence, **fields)
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
