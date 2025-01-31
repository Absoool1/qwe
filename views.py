from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.core.management import call_command
from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone
from django.utils.text import slugify
from django.db.models import Q
from django.core.files.storage import default_storage


from .models import Wallet, Campaign, LandingPage
from .forms import CampaignForm

from utils.landing_page_generator import extract_product_details, generate_landing_page
from utils.google_ads import create_google_ad
from utils.performance_analysis import analyze_performance
from utils.recommendation_engine import generate_campaign_recommendations
from utils.simulation import simulate_campaign_performance
from utils.alerts import check_performance_alerts
from utils.paypal_integration import create_payment, find_payment
from decimal import Decimal, InvalidOperation


import logging
import json
import os
import re
import random
import string
import time

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError, Completion
from requests.exceptions import RequestException
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import requests

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

from functools import lru_cache
from django.core.cache import cache
from tenacity import retry, stop_after_attempt, wait_fixed




# قائمة User-Agents عشوائية لتجنب حظر الطلبات
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
]

cache.clear()

time.sleep(random.uniform(1.5, 4.5))

# إعداد سجلات الأخطاء
logger = logging.getLogger(__name__)
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("OpenAI API key is not set. Please check your settings.")
client = OpenAI(api_key=openai_api_key)

# ============================
# الدوال العامة
# ============================

@login_required
def home(request):
    """
    عرض الصفحة الرئيسية مع معلومات المحفظة والحملات.
    """
    try:
        wallet = Wallet.objects.get(user=request.user)
        campaigns_count = Campaign.objects.filter(user=request.user).count()
        active_campaigns = Campaign.objects.filter(user=request.user, status="RUNNING").count()

        return render(request, 'home.html', {
            'wallet_balance': wallet.balance,
            'campaigns_count': campaigns_count,
            'active_campaigns': active_campaigns,
        })
    except Wallet.DoesNotExist:
        messages.error(request, "لا يوجد محفظة مرتبطة بحسابك.")
        return redirect('payment')

# ============================
@login_required
def dashboard(request):
    """
    عرض لوحة التحكم مع تفاصيل الحملات والتوصيات والتنبيهات.
    """
    try:
        campaigns = Campaign.objects.filter(user=request.user)
        performance_data = analyze_performance()
        recommendations = generate_campaign_recommendations(performance_data["detailed_performance"])
        alerts = check_performance_alerts(performance_data["detailed_performance"])

        return render(request, 'dashboard.html', {
            'campaigns': campaigns,
            'recommendations': recommendations,
            'alerts': alerts,
        })
    except Exception as e:
        logger.error(f"Error in dashboard: {e}")
        messages.error(request, "حدث خطأ أثناء تحميل لوحة التحكم.")
        return redirect('home')

# ============================
# إدارة الحملات
# ============================

@login_required
def manage_campaigns(request):
    """
    إدارة الحملات (إيقاف، استئناف، حذف).
    """
    try:
        campaigns = Campaign.objects.filter(user=request.user)

        if request.method == 'POST':
            data = json.loads(request.body)
            action = data.get('action')
            campaign_id = data.get('campaign_id')

            if action and campaign_id:
                campaign = get_object_or_404(Campaign, id=campaign_id, user=request.user)
                if action == 'pause':
                    campaign.status = "PAUSED"
                elif action == 'resume':
                    campaign.status = "RUNNING"
                elif action == 'delete':
                    campaign.delete()
                    return JsonResponse({"success": True})
                campaign.save()
                return JsonResponse({"success": True})

        return render(request, 'manage_campaigns.html', {'campaigns': campaigns})
    except Exception as e:
        logger.error(f"Error in manage_campaigns: {e}")
        messages.error(request, "حدث خطأ أثناء إدارة الحملات.")
        return redirect('dashboard')

# ============================
# المدفوعات
# ============================

@login_required
def payment_view(request):
    """
    عرض صفحة الدفع وإضافة الأموال إلى المحفظة.
    """
    try:
        wallet = Wallet.objects.get_or_create(user=request.user, defaults={"balance": 0.0})[0]

        if request.method == 'POST':
            try:
                amount = float(request.POST.get('amount'))
                if amount <= 0 or amount > 100:
                    raise ValueError("المبلغ يجب أن يكون بين 0 و 100.")

                payment = create_payment(amount)
                for link in payment.links:
                    if link.rel == "approval_url":
                        return JsonResponse({"redirect_url": link.href})
            except Exception as e:
                logger.error(f"Payment error: {e}")
                messages.error(request, "حدث خطأ أثناء الدفع.")
                return redirect('payment')

        return render(request, 'payment.html', {'wallet_balance': wallet.balance})
    except Exception as e:
        logger.error(f"Payment view error: {e}")
        return redirect('home')

# ============================
@login_required
def payment_success(request):
    """
    معالجة نجاح عملية الدفع.
    """
    try:
        payer_id = request.GET.get('PayerID')
        payment_id = request.GET.get('paymentId')

        if payer_id and payment_id:
            payment = find_payment(payment_id)
            if payment.execute({"payer_id": payer_id}):
                wallet = Wallet.objects.get(user=request.user)
                amount = float(payment.transactions[0].amount.total)
                wallet.balance += amount
                wallet.save()
                messages.success(request, "تم شحن المحفظة بنجاح!")
                return render(request, 'payment_success.html')

        raise ValueError("Invalid PayPal payment details.")
    except Exception as e:
        logger.error(f"Error in payment_success: {e}")
        messages.error(request, "حدث خطأ أثناء معالجة عملية الدفع.")
        return redirect('payment')

# ============================
@login_required
def payment_cancel(request):
    """
    معالجة إلغاء عملية الدفع.
    """
    messages.info(request, "تم إلغاء عملية الدفع.")
    return render(request, 'payment_cancel.html')

# ============================
# الحملة التسويقية
# ============================

@login_required
def marketing(request):
    """
    إنشاء حملة تسويقية جديدة.
    """
    if request.method == 'POST':
        product_url = request.POST.get('product_url')
        budget = request.POST.get('budget')

        try:
            budget = float(budget)
            if budget < 1 or budget > 100:
                raise ValueError("الميزانية يجب أن تكون بين 1 و100 دولار.")

            product_details = extract_product_details(product_url)
            landing_page = generate_landing_page(product_details)

            request.session['product_details'] = product_details
            request.session['landing_page'] = landing_page
            request.session['budget'] = budget

            messages.success(request, "تم إعداد الحملة بنجاح!")
            return redirect('preview')
        except Exception as e:
            logger.error(f"Error in marketing: {e}")
            messages.error(request, f"حدث خطأ أثناء إعداد الحملة: {e}")
            return render(request, 'marketing.html')

    return render(request, 'marketing.html')

# ============================
@login_required
def preview(request):
    """
    عرض معاينة الحملة قبل إطلاقها.
    """
    product_details = request.session.get('product_details')
    landing_page = request.session.get('landing_page')
    budget = request.session.get('budget', 0)

    if not product_details or not landing_page:
        messages.error(request, "No campaign data available for preview.")
        return redirect('marketing')

    if request.method == 'POST':
        try:
            Campaign.objects.create(
                user=request.user,
                name=product_details['title'],
                product_link=product_details['link'],
                description=product_details['description'],
                budget=budget,
                status="RUNNING",
            )
            messages.success(request, "Campaign launched successfully!")
            return redirect('dashboard')
        except Exception as e:
            logger.error(f"Error launching campaign: {e}")
            messages.error(request, f"Error launching campaign: {e}")

    return render(request, 'preview.html', {
        'product_details': product_details,
        'landing_page': landing_page,
    })

# ============================
@login_required
def generate_report(request):
    """
    إنشاء تقرير عن الحملات.
    """
    if request.method == 'POST':
        try:
            selected_fields = request.POST.getlist('fields')
            report_data = []

            campaigns = Campaign.objects.filter(user=request.user)
            for campaign in campaigns:
                report_item = {field: getattr(campaign, field, 'N/A') for field in selected_fields}
                report_data.append(report_item)

            return render(request, 'report_result.html', {"report_data": report_data})
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            messages.error(request, "حدث خطأ أثناء إنشاء التقرير.")
            return redirect('reports')

    return render(request, 'reports.html')

# ============================
@login_required
def campaigns_list(request):
    """
    عرض قائمة الحملات.
    """
    try:
        campaigns = Campaign.objects.filter(user=request.user)
        if not campaigns.exists():
            messages.warning(request, "لا توجد حملات لعرضها حاليًا.")
        return render(request, 'campaigns_list.html', {'campaigns': campaigns})
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء عرض الحملات: {e}")
        return render(request, 'campaigns_list.html', {'campaigns': []})

# ============================
@login_required
def campaign_detail(request, pk):
    """
    عرض تفاصيل حملة معينة.
    """
    campaign = get_object_or_404(Campaign, pk=pk, user=request.user)
    return render(request, 'campaign_detail.html', {'campaign': campaign})

# ============================
@login_required
def edit_campaign(request, campaign_id):
    """
    تعديل حملة معينة.
    """
    campaign = get_object_or_404(Campaign, id=campaign_id, user=request.user)

    if request.method == "POST":
        form = CampaignForm(request.POST, instance=campaign)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث الحملة بنجاح!")
            return redirect("campaigns_list")
    else:
        form = CampaignForm(instance=campaign)

    return render(request, "edit_campaign.html", {"form": form})

# ============================
@login_required
def delete_campaign(request, campaign_id):
    """
    حذف حملة معينة.
    """
    campaign = get_object_or_404(Campaign, id=campaign_id, user=request.user)
    campaign.delete()
    messages.success(request, f"تم حذف الحملة: {campaign.name}.")
    return redirect('campaigns_list')

# ============================
@csrf_exempt
def fetch_product_details(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            product_url = data.get("url", "")
            if not product_url:
                return JsonResponse({"success": False, "error": "URL is required"})
            
            result = analyze_product_with_gpt(product_url)
            if "error" in result:
                return JsonResponse({"success": False, "error": result["error"]})
            
            # حفظ البيانات في الجلسة
            request.session["product_details"] = result
            request.session.modified = True
            
            return JsonResponse({"success": True, "data": result})
        
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})
    return JsonResponse({"success": False, "error": "Invalid method"})

# ============================
@staff_member_required
def create_superuser(request):
    """
    إنشاء مستخدم فائق (superuser) إذا لم يكن موجودًا.
    """
    if not User.objects.filter(is_superuser=True).exists():
        User.objects.create_superuser(username="admin", password="admin123", email="admin@example.com")
        return HttpResponse("Superuser created! Username: admin, Password: admin123")
    return HttpResponse("Superuser already exists!")

# ============================
@staff_member_required
def run_migrations(request):
    """
    تشغيل عمليات الهجرة (migrations).
    """
    try:
        call_command("migrate")
        return JsonResponse({"status": "success", "message": "Migrations applied successfully."})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)})

# ============================
def custom_login(request):
    """
    تسجيل الدخول المخصص.
    """
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('home')
        else:
            messages.error(request, "اسم المستخدم أو كلمة المرور غير صحيحة.")
    return render(request, 'login.html')

# ============================
def test_openai_connection(request):
    """
    اختبار اتصال OpenAI API.
    """
    try:
        response = client.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Test the OpenAI API connection."}
            ]
        )
        result = response.choices[0].message.content.strip()
        return JsonResponse({"success": True, "result": result})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})

# ============================
# اختيار المنتج وتحليل الرابط
# ============================
@login_required
def product_selection(request):
    if request.method == 'POST':
        product_url = request.POST.get('product_url', '').strip()
        
        if not product_url.startswith(("http://", "https://")):
            messages.error(request, "الرجاء إدخال رابط صحيح يبدأ بـ http:// أو https://")
            return redirect('product_selection')
        
        try:
            # استخراج البيانات الأساسية
            product_info = scrape_product_info(product_url)
            logger.debug(f"Product info: {product_info}")
            if product_info.get('error'):
                messages.error(request, f"خطأ في التحليل: {product_info['error']}")
                return redirect('product_selection')
            
            # تحليل البيانات باستخدام الذكاء الاصطناعي
            gpt_data = analyze_product_with_gpt(product_info)
            logger.debug(f"GPT data: {gpt_data}")
            if "error" in gpt_data:
                messages.error(request, f"خطأ في التحليل: {gpt_data['error']}")
                return redirect('product_selection')
            
            # دمج البيانات
            merged_data = {
                **product_info,
                **gpt_data,
                'link': product_url
            }
            
            # حفظ في الجلسة
            request.session['product_details'] = merged_data
            messages.success(request, "تم تحليل المنتج بنجاح!")
            return redirect('product_preview')
            
        except Exception as e:
            logger.error(f"خطأ فني: {str(e)}", exc_info=True)
            messages.error(request, f"حدث خطأ غير متوقع: {str(e)}")
            return redirect('product_selection')

    return render(request, 'product_selection.html')
# ============================
def setup_selenium():
    options = Options()
    
    # إعدادات التهيئة المتقدمة
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    
    # تجنب الكشف عن الأتمتة
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    # User-Agent عشوائي
    options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
    
    # إضافة خيارات جديدة لتحسين الأداء
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--ignore-certificate-errors")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    # إضافة خصائص التمويه
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

#================================================
# استخراج معلومات المنتج باستخدام lru_cache للتخزين المؤقت

@retry(stop=stop_after_attempt(3), wait=wait_fixed(10))
@lru_cache(maxsize=100)
def scrape_product_info(url):
    driver = setup_selenium()
    product_data = {
        'title': 'N/A',
        'price': 'N/A',
        'reviews': ['', '', ''],
        'image_urls': [],
        'error': None
    }
    
    try:
        # إعدادات متقدمة للتحميل
        driver.set_page_load_timeout(180)  # زيادة وقت التحميل إلى 180 ثانية
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": random.choice(USER_AGENTS)
        })
        
        logger.info(f"Navigating to: {url}")
        driver.get(url)
        
        # انتظار متقدم مع تحقق من عناصر متعددة
        wait = WebDriverWait(driver, 60)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'body')))
        
        # التحقق من وجود العناصر الرئيسية
        title_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '#productTitle')))
        product_data['title'] = title_element.text.strip() or 'N/A'
        
        try:
            price_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.a-price-whole')))
            product_data['price'] = price_element.text.strip() or 'N/A'
        except TimeoutException:
            logger.warning("Price element not found, trying alternative selector")
            try:
                price_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '#priceblock_ourprice')))
                product_data['price'] = price_element.text.strip() or 'N/A'
            except TimeoutException:
                product_data['price'] = 'Price not found'
        
        # استخراج الصور
        images = driver.find_elements(By.CSS_SELECTOR, '#main-image-container img')
        product_data['image_urls'] = [img.get_attribute('src') for img in images[:5] if img.get_attribute('src')]
        
        # استخراج التقييمات
        reviews = driver.find_elements(By.CSS_SELECTOR, '[data-hook="review-collapsed"]')
        product_data['reviews'] = [review.text.strip() for review in reviews[:3]]
        
    except TimeoutException as e:
        product_data['error'] = f"لم يتم تحميل الصفحة خلال الوقت المحدد: {str(e)}"
        logger.error(f"Timeout Error: {str(e)}")
    except NoSuchElementException as e:
        product_data['error'] = f"عنصر مفقود في الصفحة: {str(e)}"
        logger.error(f"Missing Element: {str(e)}")
    except WebDriverException as e:
        product_data['error'] = f"خطأ في متصفح Selenium: {str(e)}"
        logger.error(f"Selenium Error: {str(e)}")
    except Exception as e:
        product_data['error'] = f"خطأ غير متوقع: {str(e)}"
        logger.error(f"Critical Error: {str(e)}")
    finally:
        try:
            driver.quit()
        except Exception as e:
            logger.error(f"Error closing driver: {str(e)}")
    
    return product_data
#===========================================
#===========================================
#===========================================
def analyze_product_with_gpt(product_info, max_retries=3):
    """
    Analyze product info using GPT-3.5-turbo to generate landing page content
    """
    

    # Enhanced GPT prompt with strict formatting
    gpt_prompt = f"""
    Generate HIGH-CONVERTING landing page content in STRICT JSON format:
    
    Product Details:
    - Title: {product_info.get('title', '')}
    - Price: {product_info.get('price', '')}
    - Reviews: {', '.join(product_info.get('reviews', [])[:3])}
    
    Required JSON Structure:
    {{
        "headline": "Engaging headline focusing on the benefit (max 50 characters)",
        "subheadline": "Supporting subheadline explaining the main benefit (max 100 characters)",
        "usp": "Unique Selling Proposition (max 20 words)",
        "benefits": ["Key benefit 1 (max 10 words)", "Key benefit 2 (max 10 words)", "Key benefit 3 (max 10 words)"],
        "cta": "Call-to-action phrase (3-5 words)",
        "testimonial": "Brief and impactful testimonial (max 20 words)",
        "urgency": "Short phrase to create a sense of urgency (max 10 words)"
    }}
    
    Instructions:
    1. Use persuasive marketing language
    2. Focus on emotional triggers
    3. Prioritize mobile-friendly content
    4. Use the provided product details to create relevant and specific content
    """

    for attempt in range(max_retries):
        try:
            # API call with forced JSON response
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a JSON generator. Return ONLY valid JSON matching the exact format provided."
                    },
                    {"role": "user", "content": gpt_prompt}
                ],
                temperature=0.7,
                max_tokens=500,
                response_format={"type": "json_object"}
            )

            # Extract and clean response
            raw_content = response.choices[0].message.content
            analyzed_data = json.loads(raw_content)
            logger.debug(f"Analyzed data: {analyzed_data}")

            # Validate response structure
            required_keys = [
                "headline", "subheadline", "usp",
                "benefits", "cta", "testimonial", "urgency"
            ]
            
            for key in required_keys:
                if key not in analyzed_data:
                    analyzed_data[key] = "Not available"
                    logger.warning(f"Missing key in GPT response: {key}")

            # Add original product data
            analyzed_data.update({
                "title": product_info.get("title", ""),
                "price": product_info.get("price", ""),
                "image_urls": product_info.get("image_urls", [])
            })

            return analyzed_data

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {str(e)} - Raw content: {raw_content}")
            if attempt == max_retries - 1:
                return {"error": "Failed to parse GPT response"}
            time.sleep(2 ** attempt)

        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            if attempt == max_retries - 1:
                return {"error": "Processing failed"}
            time.sleep(2 ** attempt)

    return {"error": "All attempts failed"}
    #==========================================
        #===========================================
def is_valid_url(url):
    """التحقق من صحة URL"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False



# ============================
# عرض الصفحة الموجهة
# ============================

@login_required
def product_preview(request):
    """
    عرض صفحة معاينة المنتج مع إمكانية التعديل على البيانات المخزنة في الجلسة.
    """
    # جلب بيانات المنتج من الجلسة
    product_details = request.session.get('product_details', {})

    # إذا كانت البيانات فارغة، توليد بيانات افتراضية باستخدام GPT
    if not product_details:
        try:
            product_details = generate_default_product_details()
            request.session['product_details'] = product_details
            request.session.modified = True
            print(f"Generated Product Details: {product_details}")  # Debug
        except Exception as e:
            logger.error(f"Error generating default product details: {str(e)}")
            messages.error(request, f"خطأ في توليد المحتوى: {str(e)}")
            return redirect('product_selection')

    # التأكد من وجود `slug` إذا كان مفقودًا
    if not product_details.get('slug'):
        product_details['slug'] = create_unique_slug(product_details.get('headline', 'default-title'))
        request.session['product_details'] = product_details
        request.session.modified = True
        print(f"Generated Slug: {product_details['slug']}")  # Debug

    # إذا كانت هناك طلبات POST، تحديث بيانات المنتج
    if request.method == "POST":
        try:
            update_product_details(request, product_details)
            request.session['product_details'] = product_details
            request.session.modified = True
            messages.success(request, "تم حفظ التغييرات بنجاح!")
            return redirect('product_preview')
        except Exception as e:
            logger.error(f"Error updating product details: {str(e)}")
            messages.error(request, f"حدث خطأ أثناء تحديث البيانات: {str(e)}")

    # عرض صفحة معاينة المنتج
    print(f"Final Product Details Sent to Template: {product_details}")  # Debug
    return render(request, 'product_preview.html', {
        'product_details': product_details
    })


#==============================================================
def generate_default_product_details():
    """
    توليد بيانات افتراضية للمنتج باستخدام GPT.
    """
    gpt_data = analyze_product_with_gpt("https://example.com/product")
    return {
        'link': "https://example.com/buy-now",
        'price': gpt_data.get('price', '99.99'),
        'headline': gpt_data.get('headline', 'Default Headline'),
        'subheadline': gpt_data.get('subheadline', 'Default Subheadline'),
        'usp': gpt_data.get('usp', 'Default USP'),
        'benefits': gpt_data.get('benefits', ['Benefit 1', 'Benefit 2']),
        'cta': gpt_data.get('cta', 'Buy Now'),
        'urgency': gpt_data.get('urgency', 'Limited Time Offer!'),
        'testimonials': [],
        'image_urls': [],
        'slug': create_unique_slug(gpt_data.get('headline', 'default-title'))
    }
    
    #=============================================================

def update_product_details(request, product_details):
    """
    تحديث بيانات المنتج بناءً على طلب POST.
    """
    product_details.update({
        'link': request.POST.get('purchase_url', product_details['link']),
        'price': request.POST.get('price', product_details['price']),
        'headline': request.POST.get('headline', product_details['headline']),
        'subheadline': request.POST.get('subheadline', product_details['subheadline']),
        'usp': request.POST.get('usp', product_details['usp']),
        'benefits': request.POST.get('benefits', '').split(', '),
        'cta': request.POST.get('cta', product_details['cta']),
        'urgency': request.POST.get('urgency', product_details['urgency']),
        'testimonials': [
            {
                'text': request.POST.getlist('testimonial_text[]')[i],
                'author': request.POST.getlist('testimonial_author[]')[i],
                'stars': int(request.POST.getlist('testimonial_stars[]')[i]),
                'date': request.POST.getlist('testimonial_date[]')[i]
            }
            for i in range(len(request.POST.getlist('testimonial_text[]')))
        ]
    })

    # التأكد من وجود `slug` إذا كان مفقودًا
    if not product_details.get('slug'):
        product_details['slug'] = create_unique_slug(product_details.get('headline', 'default-title'))


# ============================
# معاينه صفحة الهبوط
# ============================
@login_required
def landing_page_preview(request):
    if request.method == "POST":
        try:
            # جمع البيانات من الجلسة والنموذج
            product_details_session = request.session.get('product_details', {})
            
            # استخراج البيانات الأساسية
            form_data = {
                'headline': request.POST.get('headline', '').strip(),
                'subheadline': request.POST.get('subheadline', '').strip(),
                'purchase_url': request.POST.get('purchase_url', '').strip(),
                'price': request.POST.get('price', '').strip(),
                'usp': request.POST.get('usp', '').strip(),
                'cta': request.POST.get('cta', '').strip(),
                'urgency': request.POST.get('urgency', '').strip(),
                'benefits': [b.strip() for b in request.POST.get('benefits', '').split(',') if b.strip()],
                'testimonials': []
            }

            # معالجة التقييمات
            testimonial_texts = request.POST.getlist('testimonial_text[]')
            testimonial_authors = request.POST.getlist('testimonial_author[]')
            testimonial_stars = request.POST.getlist('testimonial_stars[]')
            testimonial_dates = request.POST.getlist('testimonial_date[]')
            
            for text, author, stars, date in zip(
                testimonial_texts, 
                testimonial_authors, 
                testimonial_stars, 
                testimonial_dates
            ):
                if text.strip() and author.strip():
                    form_data['testimonials'].append({
                        "text": text.strip(),
                        "author": author.strip(),
                        "stars": int(stars),
                        "date": date.strip()
                    })

            # التحقق من الحقول المطلوبة
            required_fields = {
                'headline': 'العنوان الرئيسي',
                'subheadline': 'الوصف الفرعي',
                'purchase_url': 'رابط الشراء',
                'price': 'السعر',
                'usp': 'نقطة البيع الفريدة',
                'cta': 'دعوة للعمل'
            }

            missing = [name for field, name in required_fields.items() if not form_data[field]]
            if missing:
                raise ValueError(f'الحقول المطلوبة: {", ".join(missing)}')

            # إنشاء صفحة الهبوط
            landing_page = LandingPage.objects.create(
                user=request.user,
                title=form_data['headline'],
                description=form_data['subheadline'],
                purchase_url=form_data['purchase_url'],
                price=form_data['price'],
                usp=form_data['usp'],
                benefits=form_data['benefits'],
                cta=form_data['cta'],
                testimonials=form_data['testimonials'],
                urgency=form_data['urgency'],
                image_urls=product_details_session.get('image_urls', []),
                is_published=False,
                slug=create_unique_slug(form_data['headline'])  # استخدام الدالة الموجودة
            )

            messages.success(request, 'تم إنشاء الصفحة بنجاح!')
            return redirect('landing_page_preview_with_slug', slug=landing_page.slug)

        except Exception as e:
            logger.error(f'Landing Page Error: {str(e)}', exc_info=True)
            messages.error(request, f'خطأ: {str(e)}')
            return redirect('product_preview')

    # عرض الصفحة
    return render(request, 'landing_preview.html', {
        'product_details': request.session.get('product_details', {})
    })
#===============================================
#-===============================================

# ============================
# تحميل الصور
# ============================
@login_required
def upload_images(request):
    if request.method == "POST":
        try:
            uploaded_files = request.FILES.getlist("image_files")
            image_urls = []

            for image_file in uploaded_files:
                # حفظ الصورة في مجلد product_images بدلًا من uploads
                file_path = os.path.join('product_images', image_file.name)
                saved_path = default_storage.save(file_path, image_file)
                
                # إضافة المسار الكامل مع MEDIA_URL
                full_url = f"{settings.MEDIA_URL}{saved_path}"
                image_urls.append(full_url)

            # حفظ الروابط في الجلسة
            product_details = request.session.get('product_details', {})
            product_details['image_urls'] = image_urls
            request.session['product_details'] = product_details

            return JsonResponse({
                "success": True,
                "image_urls": image_urls
            })

        except Exception as e:
            logger.error(f"Error uploading images: {e}")
            return JsonResponse({
                "success": False,
                "error": str(e)
            })

    return JsonResponse({
        "success": False,
        "error": "Invalid request method."
    })
# ============================
# حفظ صفحة الهبوط
# ============================

@login_required
def save_landing_page(request):
    """حفظ صفحة الهبوط مع جميع الحقول المطلوبة"""
    if request.method == "POST":
        try:
            product_details = request.session.get('product_details', {})
            
            landing_page = LandingPage.objects.create(
                user=request.user,
                title=request.POST.get('headline'),
                description=request.POST.get('subheadline'),
                purchase_url=request.POST.get('purchase_url'),
                price=request.POST.get('price'),
                usp=request.POST.get('usp'),
                benefits=product_details.get('benefits', []),
                cta=request.POST.get('cta'),
                urgency=request.POST.get('urgency'),
                image_urls=product_details.get('image_urls', []),
                slug=create_unique_slug(request.POST.get('headline'))
            )
            
            messages.success(request, "Landing page saved successfully!")
            return redirect('landing_page_preview_with_slug', slug=landing_page.slug)
            
        except Exception as e:
            messages.error(request, f"Error saving landing page: {str(e)}")
            return redirect('product_preview')
    
    return redirect('product_preview')

# ============================
# إرسال إلى Google Ads
# ============================

# ============================
# صفحة الهبوط العامة
# ============================

def get_landing_page(request, slug):
    print(f"Received request for slug: {slug}")  # إضافة هذا السطر
    try:
        landing_page = LandingPage.objects.get(slug=slug)
        data = {
            "title": landing_page.title,
            "description": landing_page.description,
            "price": str(landing_page.price),
            "usp": landing_page.usp,
            "benefits": landing_page.benefits,
            "purchase_url": landing_page.purchase_url,
            "urgency": landing_page.urgency,
            "hero_image": landing_page.hero_image.url if landing_page.hero_image else None,
        }
        return JsonResponse(data)
    except LandingPage.DoesNotExist:
        print(f"Landing page not found for slug: {slug}")
        return JsonResponse({"error": "Landing page not found"}, status=404)
    except Exception as e:
        print(f"Error in get_landing_page: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)

# ============================
# حذف الصور
# ============================
@login_required
def delete_image(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            image_url = data.get("url")
            
            # تعديل المسار لحذف الصورة من مجلد product_images
            relative_path = image_url.replace(settings.MEDIA_URL, "")
            if default_storage.exists(relative_path):
                default_storage.delete(relative_path)
            
            # حذف الصورة من الجلسة
            product_details = request.session.get('product_details', {})
            if image_url in product_details.get('image_urls', []):
                product_details['image_urls'].remove(image_url)
                request.session['product_details'] = product_details
            
            return JsonResponse({"success": True})

        except Exception as e:
            logger.error(f"Error deleting image: {e}")
            return JsonResponse({
                "success": False,
                "error": str(e)
            })

    return JsonResponse({
        "success": False,
        "error": "Invalid request method."
    })
# ============================
# حفظ تفاصيل المنتج
# ============================

@login_required
def save_product_details(request):
    """
    حفظ البيانات في قاعدة البيانات بدلًا من الجلسة.
    """
    if request.method == "POST":
        try:
            # إنشاء أو تحديث سجل المنتج
            product, created = LandingPage.objects.update_or_create(
                user=request.user,
                defaults={
                    'title': request.POST.get('headline'),
                    'description': request.POST.get('subheadline'),
                    'purchase_url': request.POST.get('purchase_url'),
                    'price': request.POST.get('price'),
                    'usp': request.POST.get('usp'),
                    'benefits': json.dumps(request.POST.get('benefits', '').split(', ')),
                    'cta': request.POST.get('cta'),
                    'urgency': request.POST.get('urgency'),
                    'image_urls': json.dumps(request.session.get('product_details', {}).get('image_urls', []))
                }
            )
            messages.success(request, "تم حفظ المنتج في قاعدة البيانات!")
            return redirect('dashboard')
        except Exception as e:
            messages.error(request, f"خطأ في الحفظ: {str(e)}")
            return redirect('product_preview')
    return redirect('product_preview')
# ============================
# معاينة صفحة الهبوط
# ============================

def public_landing_page(request):
    # يمكنك إضافة أي منطق تريده هنا
    return render(request, 'public_landing_page.html')


#===================================================================================
#===================================================================================

def create_unique_slug(title):
    base_slug = slugify(title[:45], allow_unicode=True) or "untitled"
    slug = base_slug
    counter = 1
    while LandingPage.objects.filter(slug=slug).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1
        if counter > 10:  # تقليل عدد المحاولات لتحسين الأداء
            raise ValueError("تعذر إنشاء slug فريد بعد 10 محاولات")
    return slug

#===========================================
#==========================================
@login_required
def publish_landing_page(request, slug):
    try:
        landing_page = get_object_or_404(LandingPage, slug=slug, user=request.user)
        if landing_page.is_published:
            messages.warning(request, "الصفحة منشورة بالفعل!")
            return redirect('dashboard')
        if request.method == "POST":
            landing_page.is_published = True
            landing_page.save()
            messages.success(request, "تم نشر الصفحة بنجاح!")
            return redirect('public_landing_page', slug=slug)
        return redirect('landing_page_preview_with_slug', slug=slug)
    except Exception as e:
        logger.error(f"خطأ في النشر: {str(e)}")
        messages.error(request, "حدث خطأ أثناء النشر")
        return redirect('dashboard')
    
    
#====================================================
#================================================

@login_required
def landing_page_preview_with_slug(request, slug):
    """عرض صفحة الهبوط أو إرجاع بيانات JSON"""
    try:
        # الحصول على صفحة الهبوط بناءً على slug
        landing_page = get_object_or_404(LandingPage, slug=slug, user=request.user)

        # إعداد البيانات المشتركة
        landing_page_data = {
            'title': landing_page.title,
            'description': landing_page.description,
            'purchase_url': landing_page.purchase_url,
            'price': landing_page.price,
            'usp': landing_page.usp,
            'benefits': landing_page.benefits,
            'cta': landing_page.cta,
            'urgency': landing_page.urgency,
            'image_urls': landing_page.image_urls,
            'slug': landing_page.slug
        }

        # إذا كان الطلب JSON، إرجاع البيانات
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse(landing_page_data, safe=False)

        # إذا لم يكن الطلب JSON، عرض صفحة HTML
        return render(request, 'landing_page_preview.html', {'landing_page': landing_page_data})

    except Exception as e:
        # إرجاع خطأ JSON في حالة الطلب JSON
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({'error': str(e)}, status=400)

        # رسالة خطأ عند عرض الصفحة
        messages.error(request, f"حدث خطأ: {str(e)}")
        return redirect('dashboard')

#=================================

@login_required
def save_landing_page(request):
    """حفظ صفحة الهبوط مع جميع الحقول المطلوبة"""
    if request.method == "POST":
        try:
            product_details = request.session.get('product_details', {})
            
            landing_page = LandingPage.objects.create(
                user=request.user,
                title=request.POST.get('headline'),
                description=request.POST.get('subheadline'),
                purchase_url=request.POST.get('purchase_url'),
                price=request.POST.get('price'),
                usp=request.POST.get('usp'),
                benefits=product_details.get('benefits', []),
                cta=request.POST.get('cta'),
                urgency=request.POST.get('urgency'),
                image_urls=product_details.get('image_urls', []),
                slug=create_unique_slug(request.POST.get('headline'))
            )
            
            messages.success(request, "Landing page saved successfully!")
            return redirect('landing_page_preview_with_slug', slug=landing_page.slug)
            
        except Exception as e:
            messages.error(request, f"Error saving landing page: {str(e)}")
            return redirect('product_preview')
    
    return redirect('product_preview')
