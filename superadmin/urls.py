from django.urls import path
from superadmin import views

app_name = 'superadmin'

urlpatterns = [
    # Auth & Dashboard
    path('', views.LoginPageView.as_view(), name='login'),
    path('Dashboard', views.Dashboard.as_view(), name='Dashboard'),
    path('Logout', views.Logout.as_view(), name='Logout'),
    path('StatusToggle', views.StatusToggleView.as_view(), name='StatusToggle'),
    path('SequenceUpdate', views.SequenceUpdateView.as_view(), name='SequenceUpdate'),
    path('Profile', views.ProfileView.as_view(), name='Profile'),

    # Blog Module
    path('Blog-Categories', views.BlogCategoryList.as_view(), name='BlogCategoryList'),
    path('Blog-Category-Add', views.BlogCategoryAdd.as_view(), name='BlogCategoryAdd'),
    path('Blog-Category-Edit/<int:id>', views.BlogCategoryAdd.as_view(), name='BlogCategoryEdit'),
    path('Blog-Category-Delete/<int:id>', views.BlogCategoryDelete.as_view(), name='BlogCategoryDelete'),
    path('Blogs', views.BlogList.as_view(), name='BlogList'),
    path('Blog-Add', views.BlogAdd.as_view(), name='BlogAdd'),
    path('Blog-Edit/<int:id>', views.BlogAdd.as_view(), name='BlogEdit'),
    path('Blog-Delete/<int:id>', views.BlogDelete.as_view(), name='BlogDelete'),
    path('Editor-Image-Upload', views.EditorImageUpload.as_view(), name='EditorImageUpload'),

    # Enquiries Module
    path('Enquiries', views.EnquiryList.as_view(), name='EnquiryList'),
    path('Enquiries-Export', views.EnquiryExport.as_view(), name='EnquiryExport'),
    path('Enquiry-Read/<int:id>', views.EnquiryMarkRead.as_view(), name='EnquiryMarkRead'),
    path('Enquiry-Delete/<int:id>', views.EnquiryDelete.as_view(), name='EnquiryDelete'),

    # Career Applications Module
    path('Career-Applications', views.CareerApplicationList.as_view(), name='CareerApplicationList'),
    path('Career-Applications-Export', views.CareerApplicationExport.as_view(), name='CareerApplicationExport'),
    path('Career-Application/<int:id>', views.CareerApplicationDetail.as_view(), name='CareerApplicationDetail'),
    path('Career-Application-Status/<int:id>', views.CareerApplicationStatus.as_view(), name='CareerApplicationStatus'),
    path('Career-Application-CV/<int:id>', views.CareerApplicationCV.as_view(), name='CareerApplicationCV'),
    path('Career-Application-Delete/<int:id>', views.CareerApplicationDelete.as_view(), name='CareerApplicationDelete'),
]
