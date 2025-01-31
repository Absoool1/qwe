from django.db import models
from django.contrib.auth.models import User
from autoslug import AutoSlugField
from django.utils.text import slugify
import random
import string



class ProductDetails:
    testimonials = models.JSONField(default=list)  # تخزين البيانات كـ JSON


class LandingPage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255, verbose_name="العنوان")
    description = models.TextField(verbose_name="الوصف")
    purchase_url = models.URLField(verbose_name="رابط الشراء")
   # hero_image = models.ImageField(upload_to="hero_images/", blank=True, null=True, verbose_name="الصورة الرئيسية")
    hero_image = models.ImageField(upload_to="hero_images/", blank=True, null=True, verbose_name="main pic ")
    slug = models.SlugField(unique=True, verbose_name="الرابط الفريد")
    created_at = models.DateTimeField(auto_now_add=True)
    is_published = models.BooleanField(default=False)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    usp = models.CharField(max_length=255, verbose_name="نقطة البيع الفريدة")
    benefits = models.JSONField(default=list, verbose_name="الفوائد الرئيسية")
    cta = models.CharField(max_length=255, verbose_name="دعوة للعمل")
    testimonials = models.JSONField(default=list, verbose_name="تقييمات العملاء")
    urgency = models.CharField(max_length=255, verbose_name="عنصر الاستعجال")

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title[:50])
            unique_slug = base_slug
            num = 1
            while LandingPage.objects.filter(slug=unique_slug).exists():
                unique_slug = f'{base_slug}-{num}'
                num += 1
            self.slug = unique_slug
        super().save(*args, **kwargs)


    def __str__(self):
        return self.title

# Wallet Model
class Wallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)

    class Meta:
        verbose_name = "User Wallet"
        verbose_name_plural = "User Wallets"

    def __str__(self):
        return f"{self.user.username}'s Wallet"

    def add_funds(self, amount):
        """
        إضافة رصيد إلى المحفظة.
        """
        if amount < 0:
            raise ValueError("Amount to add must be positive.")
        self.balance += amount
        self.save()

    def deduct_funds(self, amount):
        """
        خصم رصيد من المحفظة.
        """
        if amount < 0:
            raise ValueError("Amount to deduct must be positive.")
        if self.balance >= amount:
            self.balance -= amount
            self.save()
        else:
            raise ValueError("Insufficient balance.")

# Campaign Model
class Campaign(models.Model):
    STATUS_CHOICES = [
        ('RUNNING', 'Running'),
        ('PAUSED', 'Paused'),
        ('COMPLETED', 'Completed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="campaigns")
    name = models.CharField(max_length=255, verbose_name="Campaign Name")
    product_link = models.URLField(verbose_name="Product Link")
    description = models.TextField(verbose_name="Description")
    budget = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Budget")
    budget_spent = models.DecimalField(max_digits=10, decimal_places=2, default=0.0, verbose_name="Budget Spent")
    clicks = models.PositiveIntegerField(default=0, verbose_name="Clicks")
    conversions = models.PositiveIntegerField(default=0, verbose_name="Conversions")
    cost_per_conversion = models.DecimalField(max_digits=10, decimal_places=2, default=0.0, verbose_name="Cost Per Conversion")
    roi = models.FloatField(default=0.0, verbose_name="Return on Investment (ROI)")
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='RUNNING',
        verbose_name="Status"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Last Updated")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'name'], name='unique_campaign_per_user')
        ]

    def calculate_roi(self):
        """
        حساب العائد على الاستثمار (ROI).
        """
        if self.budget_spent > 0:
            self.roi = (self.conversions - self.budget_spent) / self.budget_spent
        else:
            self.roi = 0.0

    def save(self, *args, **kwargs):
        """
        إعادة حساب الحقول المستندة إلى القيم الأخرى عند الحفظ.
        """
        self.cost_per_conversion = (
            self.budget_spent / self.conversions if self.conversions > 0 else 0.0
        )
        self.calculate_roi()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

# Payment Model
class Payment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="USD")  # دعم العملات
    description = models.TextField(blank=True, null=True, verbose_name="Payment Description")
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment of {self.amount} {self.currency} by {self.user.username}"
