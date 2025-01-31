from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # ======== المسارات العامة ========
    path('login/', views.custom_login, name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),
    path('password_change/', auth_views.PasswordChangeView.as_view(template_name='password_change.html'), name='password_change'),
    path('password_change/done/', auth_views.PasswordChangeDoneView.as_view(template_name='password_change_done.html'), name='password_change_done'),
    
    # ======== لوحة التحكم وإدارة الحملة ========
    path('dashboard/', views.dashboard, name='dashboard'),
    path('campaigns/', views.campaigns_list, name='campaigns_list'),
    path('campaigns/manage/', views.manage_campaigns, name='manage_campaigns'),
    path('campaigns/<int:pk>/', views.campaign_detail, name='campaign_detail'),
    path("campaigns/edit/<int:campaign_id>/", views.edit_campaign, name="edit_campaign"),
    path('campaigns/delete/<int:campaign_id>/', views.delete_campaign, name='delete_campaign'),

    # ======== إدارة الدفع ========
    path('payment/', views.payment_view, name='payment'),
    path('payment/success/', views.payment_success, name='payment_success'),
    path('payment/cancel/', views.payment_cancel, name='payment_cancel'),

    # ======== أدوات خاصة ========
    path("run-migrations/", views.run_migrations, name="run_migrations"),
    path('create-superuser/', views.create_superuser, name='create_superuser'),
    
    # ======== الصفحات الثابتة ========
    path('contact/', TemplateView.as_view(template_name="contact.html"), name='contact'),
    path('features/', TemplateView.as_view(template_name="features.html"), name='features'),
    path('', TemplateView.as_view(template_name="home.html"), name='home'),
    path('about_us/', TemplateView.as_view(template_name="about_us.html"), name='about_us'),
    path('privacy-policy/', TemplateView.as_view(template_name="privacy_policy.html"), name="privacy_policy"),
    path('welcome_amazon/', TemplateView.as_view(template_name="welcome_amazon.html"), name="welcome_amazon"),
    path('marketing/', TemplateView.as_view(template_name="marketing.html"), name='marketing'),

    # ======== إدارة المنتجات وصفحات الهبوط ========
    path('api/fetch-product-details/', views.fetch_product_details, name='fetch_product_details'),
    path('product_selection/', views.product_selection, name='product_selection'),
    path('product_preview/', views.product_preview, name='product_preview'),
    path('save_product_details/', views.save_product_details, name='save_product_details'),
    path('upload_images/', views.upload_images, name='upload_images'),
    path('delete_image/', views.delete_image, name='delete_image'),

    # ======== إدارة صفحات الهبوط ========
    path('landing_page_preview/', views.landing_page_preview, name='landing_page_preview'),
    path('lp/<slug:slug>/', views.landing_page_preview_with_slug, name='landing_page_preview_with_slug'),
    path('publish/<slug:slug>/', views.publish_landing_page, name='publish_landing'),
    path('public-landing-page/', views.public_landing_page, name='public_landing_page'),
    path('api/get-landing-page/<slug:slug>/', views.get_landing_page, name='get_landing_page'),
    path('api/update-landing-page/<slug>/', views.save_landing_page, name='update_landing_page'),
    path('save_landing_page/', views.save_landing_page, name='save_landing_page'),
]

# ======== إعدادات الوسائط ========
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
