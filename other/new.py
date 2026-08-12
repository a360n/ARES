from machine import Pin, PWM
import time

# --- [تعديل برمي] إعدادات دبابيس المشغل الأيمن (Right Driver) ---
# تم تبديل التسميات برمجياً لتطابق توصيل أسلاكك الواقعي
ENA_R = PWM(Pin(11)) # أصبح يتحكم بالمحرك الأمامي الأيمن برمجياً (ENB في الواقع)
IN1_R = Pin(13, Pin.OUT) # (IN3 في الواقع)
IN2_R = Pin(12, Pin.OUT) # (IN4 في الواقع)

IN3_R = Pin(17, Pin.OUT) # أصبح يتحكم بالمحرك الخلفي الأيمن برمجياً (IN1 في الواقع)
IN4_R = Pin(16, Pin.OUT) # (IN2 في الواقع)
ENB_R = PWM(Pin(18)) # (ENA في الواقع)

# --- إعدادات دبابيس المشغل الأيسر (Left Driver) ---
ENA_L = PWM(Pin(2))  
IN1_L = Pin(3, Pin.OUT)
IN2_L = Pin(4, Pin.OUT)

IN3_L = Pin(5, Pin.OUT)  
IN4_L = Pin(6, Pin.OUT)
ENB_L = PWM(Pin(7))

# ضبط تردد الـ PWM لجميع المشغلات الأربعة (1000 هرتز)
for pwm in [ENA_R, ENB_R, ENA_L, ENB_L]:
    pwm.freq(1000)

def set_speed(pwm, speed_percentage):
    pwm.duty_u16(int((speed_percentage / 100) * 65535))

def stop_all():
    IN1_R.value(0); IN2_R.value(0); IN3_R.value(0); IN4_R.value(0)
    IN1_L.value(0); IN2_L.value(0); IN3_L.value(0); IN4_L.value(0)
    set_speed(ENA_R, 0); set_speed(ENB_R, 0)
    set_speed(ENA_L, 0); set_speed(ENB_L, 0)
    print("إيقاف...")

TEST_SPEED = 65

try:
    print("=== بدء الفحص المتسلسل المعدل برمجياً لـ ARES ===")
    time.sleep(1)

    # ١- المحرك الامامي الايمن للامام
    print("1- المحرك الأمامي الأيمن -> للأمام")
    set_speed(ENA_R, TEST_SPEED)
    IN1_R.value(1); IN2_R.value(0)
    time.sleep(2); stop_all(); time.sleep(1)

    # ٢- المحرك الأمامي الأيمن للخلف
    print("2- المحرك الأمامي الأيمن -> للخلف")
    set_speed(ENA_R, TEST_SPEED)
    IN1_R.value(0); IN2_R.value(1)
    time.sleep(2); stop_all(); time.sleep(1)

    # ٣ - المحرك الخلفي الايمن للامام
    print("3- المحرك الخلفي الأيمن -> للأمام")
    set_speed(ENB_R, TEST_SPEED)
    IN3_R.value(0); IN4_R.value(1)
    time.sleep(2); stop_all(); time.sleep(1)

    # ٤ - المحرك الخلفي الأيمن للخلف
    print("4- المحرك الخلفي الأيمن -> للخلف")
    set_speed(ENB_R, TEST_SPEED)
    IN3_R.value(1); IN4_R.value(0)
    time.sleep(2); stop_all(); time.sleep(1)

    # ٥- محركي الايمن للامام
    print("5- الجانب الأيمن بالكامل -> للأمام")
    set_speed(ENA_R, TEST_SPEED)
    set_speed(ENB_R, TEST_SPEED)
    IN1_R.value(1); IN2_R.value(0)
    IN3_R.value(0); IN4_R.value(1)
    time.sleep(2.5); stop_all(); time.sleep(1)

    # ٦ - محركي الأيمن للخلف
    print("6- الجانب الأيمن بالكامل -> للخلف")
    set_speed(ENA_R, TEST_SPEED)
    set_speed(ENB_R, TEST_SPEED)
    IN1_R.value(0); IN2_R.value(1)
    IN3_R.value(1); IN4_R.value(0)
    time.sleep(2.5); stop_all(); time.sleep(1)

    # ٧- المحرك الامامي الايسر للامام ([تعديل برمي] تم عكس الـ values لتتحرك للأمام فعلياً)
    print("7- المحرك الأمامي الأيسر -> للأمام")
    set_speed(ENA_L, TEST_SPEED)
    IN1_L.value(0); IN2_L.value(1)
    time.sleep(2); stop_all(); time.sleep(1)

    # ٨- المحرك الأمامي الأيسر للخلف
    print("8- المحرك الأمامي الأيسر -> للخلف")
    set_speed(ENA_L, TEST_SPEED)
    IN1_L.value(1); IN2_L.value(0)
    time.sleep(2); stop_all(); time.sleep(1)

    # ٩ - المحرك الخلفي الايسر للامام ([تعديل برمي] تم عكس الـ values)
    print("9- المحرك الخلفي الأيسر -> للأمام")
    set_speed(ENB_L, TEST_SPEED)
    IN3_L.value(0); IN4_L.value(1)
    time.sleep(2); stop_all(); time.sleep(1)

    # ١٠ - المحرك الخلفي الأيسر للخلف
    print("10- المحرك الخلفي الأيسر -> للخلف")
    set_speed(ENB_L, TEST_SPEED)
    IN3_L.value(1); IN4_L.value(0)
    time.sleep(2); stop_all(); time.sleep(1)

    # ١١- محركي الايسر للامام
    print("11- الجانب الأيسر بالكامل -> للأمام")
    set_speed(ENA_L, TEST_SPEED)
    set_speed(ENB_L, TEST_SPEED)
    IN1_L.value(0); IN2_L.value(1)
    IN3_L.value(0); IN4_L.value(1)
    time.sleep(2.5); stop_all(); time.sleep(1)

    # ١٢ - محركي الأيسر للخلف
    print("12- الجانب الأيسر بالكامل -> للخلف")
    set_speed(ENA_L, TEST_SPEED)
    set_speed(ENB_L, TEST_SPEED)
    IN1_L.value(1); IN2_L.value(0)
    IN3_L.value(1); IN4_L.value(0)
    time.sleep(2.5); stop_all()

    print("\n=== انتهى فحص الحركة البرمجي بنجاح تام! ===")

except KeyboardInterrupt:
    stop_all()