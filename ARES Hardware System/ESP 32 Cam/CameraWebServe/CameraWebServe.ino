#include <Arduino.h>
#include "esp_camera.h"
#include <WiFi.h>
#include <mutex>
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

// ============================================================================
// 1. إجبار الكود على استخدام موديل AI Thinker وتخطي فخ التعارض
// ============================================================================
#define CAMERA_MODEL_AI_THINKER

#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

#define TX_PIN 14  // جعل الدبوس 14 الحر هو المرسل (TX)
#define RX_PIN 3   // إبقاء الـ RX القياسي كما هو (U0RXD)

// متغير عالمي مشترك لتخزين أحدث قراءة قادمة من البيكو مع حماية المتغير للـ Multithreading
String latestTelemetry = "DATA:0,0,0,0,0,No Fix,No Fix,0,0,0";
std::mutex telemetryMutex;

const char *ssid = "ARES-CAMERA";
const char *password = "ARES2026";

void startCameraServer();
void setupLedFlash(); // إعلان دالة تهيئة الفلاش الخارجية
void setupServos();   // إعلان دالة تهيئة محركات السيرفو

void setup() {
  // ⚡ تعطيل كاشف هبوط الفولت (Brownout Detector) لمنع إعادة إقلاع الشريحة المستمرة عند تشغيل راديو الواي فاي
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

  Serial.begin(115200, SERIAL_8N1, RX_PIN, TX_PIN);
  Serial.setTimeout(50); // منع الاختناق في قراءة السيريال
  
  // تهيئة منفذ السيريال الثاني للتصحيح عبر USB ومراقبة السجلات
  Serial2.begin(115200, SERIAL_8N1, -1, 1); // RX = -1 (غير مستخدم), TX = 1 (U0TXD الافتراضي للـ USB)
  Serial2.println("\n[DEBUG] تم تشغيل منفذ مراقبة السجلات عبر USB بنجاح!");
  
  Serial.setDebugOutput(false);
  Serial2.setDebugOutput(true);
  Serial2.println("[DEBUG] بدء تهيئة عين الروبوت ARES...");
  
  // 📡 [إطلاق الواي فاي أولاً]: تفعيل نقطة الوصول في بداية setup لضمان ظهور الشبكة حتى لو فشلت الكاميرا
  Serial2.println("[+] جاري إطلاق شبكة الواي فاي (ARES-CAMERA)...");
  WiFi.mode(WIFI_AP);
  bool apOk = WiFi.softAP(ssid, password, 1, 0, 4);
  if (apOk) {
    Serial2.printf("[+] تم إطلاق الشبكة بنجاح! الـ IP: %s\n", WiFi.softAPIP().toString().c_str());
  } else {
    Serial2.println("[-] فشل إطلاق شبكة الواي فاي!");
  }
  delay(200);

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;  
  config.frame_size = FRAMESIZE_VGA;
  config.fb_location = CAMERA_FB_IN_DRAM;
  config.fb_count = 1;
  config.jpeg_quality = 12;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial2.printf("[-] تنبيه: فشلت تهيئة سنسور الكاميرا (رمز: 0x%x)، ولكن الواي فاي يعمل الآن بحالة ممتازة!\n", err);
  } else {
    sensor_t *s = esp_camera_sensor_get();
    s->set_vflip(s, 1);   // تفعيل القلب الرأسي
    s->set_hmirror(s, 1); // تفعيل المرآة الأفقية
  }

  // 🌟 [تفعيل عتاد الفلاش الحاسم]: ربط معمارية الـ LED بالـ PWM عند الإقلاع
  setupLedFlash();

  // 🎥 تهيئة محركات السيرفو الخاصة بالكاميرا
  setupServos();

  startCameraServer();

  Serial2.println("\n==================================================");
  Serial2.println("[نجاح] كاميرا الروبوت ARES جاهزة ومستقرة ومستمعة للتليمتري!");
  Serial2.println("==================================================");
}

void loop() {
  if (Serial.available()) {
    String input = Serial.readStringUntil('\n');
    input.trim();
    if (input.startsWith("DATA:")) {
      {
        std::lock_guard<std::mutex> lock(telemetryMutex);
        latestTelemetry = input;
      }
      Serial2.printf("[Pico Telemetry] %s\n", input.c_str());
    }
  }
  delay(10); 
}