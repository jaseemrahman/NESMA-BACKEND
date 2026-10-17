from django.urls import path
from website import api_views

app_name = 'website'

urlpatterns = [
    # ── Media centre (blogs) ─────────────────────────────────────────────────
    path('blog-categories/', api_views.BlogCategoryListView.as_view(), name='api_blog_categories'),
    path('blogs/', api_views.BlogListView.as_view(), name='api_blogs'),
    path('blogs/<slug:slug>/', api_views.BlogDetailView.as_view(), name='api_blog_detail'),

    # ── Forms ────────────────────────────────────────────────────────────────
    path('enquiry/', api_views.EnquiryCreateView.as_view(), name='api_enquiry'),
    path('career-options/', api_views.CareerOptionsView.as_view(), name='api_career_options'),
    path('career-application/', api_views.CareerApplicationCreateView.as_view(), name='api_career_application'),
]
