import machine
import utime
import math
import dht

# ============================================================================
# 1. إعداد دبابيس المحركات (مطابقة للجدول 100%)
# ============================================================================
# ============================================================================
# 1. إعداد خطوط السيريال (UART0 و UART1) أولاً لمنع أي استيلاء تلقائي على الدبابيس المشتركة
# ============================================================================
# خط السيريال الرئيسي مع الكاميرا (GP0 -> TX, GP1 -> RX)
uart = machine.UART(0, baudrate=115200, tx=machine.Pin(0), rx=machine.Pin(1))

# خط الـ GPS الاستقبالي (UART1)
# ⚠️ تنبيه هام: تم تعيين دبابيس الـ TX لـ UART1 يدوياً إلى GP24 غير المستخدم وتعيين الـ RX إلى GP21
# وتهيئة UART1 هنا أولاً لكي لا يستولي افتراضياً على دبابيس المحرك الأيسر (GP4, GP5, GP6, GP7)
gps_uart = machine.UART(1, baudrate=9600, rx=machine.Pin(21), tx=machine.Pin(24))

# ============================================================================
# 2. إعداد دبابيس المحركات (Left Driver & Right Driver) بعد تهيئة السيريال
# ============================================================================
# المشغل الأيسر (Left Driver) - التوصيل الجديد
pwm_front_left = machine.PWM(machine.Pin(2))   # سرعة الأمامية اليسرى (GP2)
in1_front_left = machine.Pin(3, machine.Pin.OUT, value=0) # اتجاه الأمامية اليسرى 1 (GP3)
in2_front_left = machine.Pin(4, machine.Pin.OUT, value=0) # اتجاه الأمامية اليسرى 2 (GP4)
in3_rear_left = machine.Pin(5, machine.Pin.OUT, value=0) # اتجاه الخلفية اليسرى 1 (GP5)
in4_rear_left = machine.Pin(6, machine.Pin.OUT, value=0) # اتجاه الخلفية اليسرى 2 (GP6)
pwm_rear_left = machine.PWM(machine.Pin(7))   # سرعة الخلفية اليسرى (GP7)

# المشغل الأيمن (Right Driver) - التوصيل الجديد
pwm_front_right = machine.PWM(machine.Pin(11))  # سرعة الأمامية اليمنى (GP11)
in1_front_right = machine.Pin(13, machine.Pin.OUT, value=0) # اتجاه الأمامية اليمنى 1 (GP13)
in2_front_right = machine.Pin(12, machine.Pin.OUT, value=0) # اتجاه الأمامية اليمنى 2 (GP12)
in3_rear_right = machine.Pin(17, machine.Pin.OUT, value=0) # اتجاه الخلفية اليمنى 1 (GP17)
in4_rear_right = machine.Pin(16, machine.Pin.OUT, value=0) # اتجاه الخلفية اليمنى 2 (GP16)
pwm_rear_right = machine.PWM(machine.Pin(18)) # سرعة الخلفية اليمنى (GP18)

for pwm in [pwm_front_left, pwm_rear_left, pwm_front_right, pwm_rear_right]:
    pwm.freq(1000)

# ============================================================================
# 3. إعداد الحساسات والمشفرات طبقاً لجدول العتاد الفعلي
# ============================================================================
# أ) حساس المسافة الـ Ultrasonic
trig = machine.Pin(20, machine.Pin.OUT) # تم إبقاء Trig على 20 وتطهيره من تداخل GPS
echo = machine.Pin(8, machine.Pin.IN)   # سلك علامة (2) عبر مقسم الجهد

# ب) حساسات الغاز التماثلية والبطارية (ADC)
adc_battery = machine.ADC(machine.Pin(26)) # سلك أبيض منفرد - مقسم جهد البطارية
adc_mq9 = machine.ADC(machine.Pin(27))     # سلك علامة (1) - حساس MQ-9
adc_mq135 = machine.ADC(machine.Pin(28))   # سلك علامة (4) - حساس MQ-135


# د) حساس الـ DHT22 الرقمي
dht_sensor = dht.DHT22(machine.Pin(22)) # سلك علامة (3)

# هـ) دبابيس المشفرات الأربعة الفعالة (Encoders) وحساب الـ Ticks
enc_rr_pin = machine.Pin(9, machine.Pin.IN, machine.Pin.PULL_UP)  # سلك أبيض - عجلة خلفية يمنى
enc_fr_pin = machine.Pin(10, machine.Pin.IN, machine.Pin.PULL_UP) # سلك أبيض - عجلة أمامية يمنى
enc_fl_pin = machine.Pin(14, machine.Pin.IN, machine.Pin.PULL_UP) # سلك أبيض - عجلة أمامية يسرى
enc_rl_pin = machine.Pin(15, machine.Pin.IN, machine.Pin.PULL_UP) # سلك أبيض - عجلة خلفية يسرى

# عدادات النبضات مستقلة لكل محرك
ticks_RR = 0; ticks_FR = 0; ticks_FL = 0; ticks_RL = 0

def count_rr(pin): global ticks_RR; ticks_RR += 1
def count_fr(pin): global ticks_FR; ticks_FR += 1
def count_fl(pin): global ticks_FL; ticks_FL += 1
def count_rl(pin): global ticks_RL; ticks_RL += 1

enc_rr_pin.irq(trigger=machine.Pin.IRQ_RISING, handler=count_rr)
enc_fr_pin.irq(trigger=machine.Pin.IRQ_RISING, handler=count_fr)
enc_fl_pin.irq(trigger=machine.Pin.IRQ_RISING, handler=count_fl)
enc_rl_pin.irq(trigger=machine.Pin.IRQ_RISING, handler=count_rl)

# ============================================================================
# 3. دالات قراءة واستخلاص البيانات (Telemetry Functions)
# ============================================================================
last_ultrasonic_debug = 0

def get_distance():
    global last_ultrasonic_debug
    duration = -1
    # محاولة القياس مرتين لضمان استقرار الإشارة والتغلب على الضوضاء
    for attempt in range(2):
        trig.value(0)
        utime.sleep_us(5)
        
        # إرسال نبضة تفعيل مدتها 10 ميكروثانية
        trig.value(1)
        utime.sleep_us(10)
        trig.value(0)
        
        # قياس النبضة المرتدة مهلة زمنية 30,000 ميكروثانية (تغطي حتى 500 سم)
        duration = machine.time_pulse_us(echo, 1, 30000)
        
        if duration > 0:
            distance = (duration * 0.0343) / 2
            return round(distance, 1)
            
        utime.sleep_us(2000)
        
    # إذا فشل الحساس في إرجاع النبضة، يتم طباعة رسالة تشخيصية في الكونسول مرة كل 5 ثوانٍ
    now = utime.ticks_ms()
    if utime.ticks_diff(now, last_ultrasonic_debug) > 5000:
        print(f"[Ultrasonic DIAGNOSTIC] Pulse timeout (Error code: {duration}). Check 5V VCC, Trig (GP20), and Echo (GP8) voltage divider.")
        last_ultrasonic_debug = now
        
    return 400.0
def get_battery_voltage():
    raw = adc_battery.read_u16()
    voltage_adc = (raw / 65535) * 3.3
    return round(voltage_adc * 4.12, 1)

last_lat, last_lng = "No Fix", "No Fix"
gps_debug_timer = 0

def parse_gps():
    global last_lat, last_lng, gps_debug_timer
    while gps_uart.any():
        try:
            raw_line = gps_uart.readline()
            if raw_line:
                line_str = raw_line.decode().strip()
                if line_str.startswith("$"):
                    current_time = utime.ticks_ms()
                    # طباعة الجملة المستلمة للتأكد من التوصيل المادي (مرة كل 3 ثوانٍ لتجنب امتلاء الكونسل)
                    if utime.ticks_diff(current_time, gps_debug_timer) > 3000:
                        print(f"[GPS RAW] {line_str}")
                        gps_debug_timer = current_time
                    
                    if "RMC" in line_str:
                        parts = line_str.split(',')
                        if len(parts) > 6:
                            status = parts[2]
                            if status == 'A':
                                raw_lat = parts[3]
                                lat_dir = parts[4]
                                raw_lng = parts[5]
                                lng_dir = parts[6]
                                if len(raw_lat) >= 2 and len(raw_lng) >= 3:
                                    last_lat = raw_lat[:2] + "°" + raw_lat[2:] + " " + lat_dir
                                    last_lng = raw_lng[:3] + "°" + raw_lng[3:] + " " + lng_dir
                                    print(f"[GPS LOG] Fix acquired! Lat: {last_lat}, Lng: {last_lng}")
                            elif status == 'V':
                                if utime.ticks_diff(current_time, gps_debug_timer) > 3000:
                                    print("[GPS LOG] GPS module is communicating, but waiting for satellite lock (Void status). Try going outdoors.")
                                    gps_debug_timer = current_time
        except Exception as e:
            current_time = utime.ticks_ms()
            if utime.ticks_diff(current_time, gps_debug_timer) > 3000:
                print(f"[GPS ERROR] Decoding error or noise: {e}")
                gps_debug_timer = current_time
            pass
    return last_lat, last_lng

# ============================================================================
# 4. دالات التحكم بالحركة (مستقرة وموزونة)
# ============================================================================
last_applied_speed = -1

def set_speed(speed_val):
    global last_applied_speed
    speed_int = int(speed_val)
    if speed_int != last_applied_speed:
        last_applied_speed = speed_int
        
        # حساب قيمة الـ duty الافتراضية
        duty = int((speed_int / 100) * 65535)
        
        # حساب قيمة الـ duty مع تعويض (+8%) للعجلة المتصلة بـ GP2 (الأمامية اليسرى حالياً) لتجاوز الاحتكاك
        # إذا كنت تريد نقل التعويض للعجلة الخلفية اليسرى (GP7) بدلاً من الأمامية اليسرى (GP2)، يمكنك تعديل الأسطر أدناه:
        speed_comp = min(speed_int + 8, 100) if speed_int > 0 else 0
        duty_comp = int((speed_comp / 100) * 65535)
        
        pwm_front_left.duty_u16(duty_comp) # GP2 - مع التعويض
        pwm_rear_left.duty_u16(duty)       # GP7
        pwm_front_right.duty_u16(duty)     # GP11
        pwm_rear_right.duty_u16(duty)      # GP18

def robot_forward():
    in1_front_left.value(1); in2_front_left.value(0)
    in3_rear_left.value(1); in4_rear_left.value(0)
    in1_front_right.value(0); in2_front_right.value(1)
    in3_rear_right.value(1); in4_rear_right.value(0)
    print(f"[DEBUG_PINS] Forward -> LeftFront({in1_front_left.value()},{in2_front_left.value()}) LeftRear({in3_rear_left.value()},{in4_rear_left.value()}) | RightFront({in1_front_right.value()},{in2_front_right.value()}) RightRear({in3_rear_right.value()},{in4_rear_right.value()})")

def robot_backward():
    in1_front_left.value(0); in2_front_left.value(1)
    in3_rear_left.value(0); in4_rear_left.value(1)
    in1_front_right.value(1); in2_front_right.value(0)
    in3_rear_right.value(0); in4_rear_right.value(1)
    print(f"[DEBUG_PINS] Backward -> LeftFront({in1_front_left.value()},{in2_front_left.value()}) LeftRear({in3_rear_left.value()},{in4_rear_left.value()}) | RightFront({in1_front_right.value()},{in2_front_right.value()}) RightRear({in3_rear_right.value()},{in4_rear_right.value()})")

def robot_left():
    in1_front_left.value(0); in2_front_left.value(1)
    in3_rear_left.value(0); in4_rear_left.value(1)
    in1_front_right.value(0); in2_front_right.value(1)
    in3_rear_right.value(1); in4_rear_right.value(0)
    print(f"[DEBUG_PINS] TurnLeft -> LeftFront({in1_front_left.value()},{in2_front_left.value()}) LeftRear({in3_rear_left.value()},{in4_rear_left.value()}) | RightFront({in1_front_right.value()},{in2_front_right.value()}) RightRear({in3_rear_right.value()},{in4_rear_right.value()})")

def robot_right():
    in1_front_left.value(1); in2_front_left.value(0)
    in3_rear_left.value(1); in4_rear_left.value(0)
    in1_front_right.value(1); in2_front_right.value(0)
    in3_rear_right.value(0); in4_rear_right.value(1)
    print(f"[DEBUG_PINS] TurnRight -> LeftFront({in1_front_left.value()},{in2_front_left.value()}) LeftRear({in3_rear_left.value()},{in4_rear_left.value()}) | RightFront({in1_front_right.value()},{in2_front_right.value()}) RightRear({in3_rear_right.value()},{in4_rear_right.value()})")

def robot_stop():
    set_speed(0)
    in1_front_left.value(0); in2_front_left.value(0)
    in3_rear_left.value(0); in4_rear_left.value(0)
    in1_front_right.value(0); in2_front_right.value(0)
    in3_rear_right.value(0); in4_rear_right.value(0)
    print(f"[DEBUG_PINS] Stop -> LeftFront({in1_front_left.value()},{in2_front_left.value()}) LeftRear({in3_rear_left.value()},{in4_rear_left.value()}) | RightFront({in1_front_right.value()},{in2_front_right.value()}) RightRear({in3_rear_right.value()},{in4_rear_right.value()})")

robot_stop()
print("[+] تم مطابقة الدبابيس 100%... نظام ARES جاهز للتحليق العتادي!")

last_telemetry_time = utime.ticks_ms()
# ============================================================================
# 5. الحلقة الرئيسية المحصنة (حركة فورية + تسارع تدريجي + معالجة ذكية للأخطاء)
# ============================================================================
current_direction = 'x'
direction_start_time = 0
max_target_speed = 0

while True:
    if uart.any():
        try:
            raw_data = uart.read().decode().strip()
            if len(raw_data) > 0:
                cmd = raw_data[-1]  # تنفيذ آخر أمر متاح فوراً لمنع تعليق الروبوت
                if cmd != current_direction:
                    current_direction = cmd
                    direction_start_time = utime.ticks_ms()
                    print(f"[Pico LOG] New movement command received: '{cmd}'")
                    if cmd == 'w':
                        max_target_speed = 25  # تخفيض السرعة القصوى للأمام إلى 25%
                        robot_forward()
                    elif cmd == 's':
                        max_target_speed = 25  # تخفيض السرعة القصوى للخلف إلى 25%
                        robot_backward()
                    elif cmd == 'a':
                        max_target_speed = 30  # تخفيض سرعة الدوران إلى 30%
                        robot_left()
                    elif cmd == 'd':
                        max_target_speed = 30  # تخفيض سرعة الدوران إلى 30%
                        robot_right()
                    elif cmd == 'x':
                        max_target_speed = 0
                        robot_stop()
        except Exception as e:
            print(f"[Pico ERROR] Serial parsing error: {e}")
            pass

    # حساب وتطبيق منحنى التسارع التدريجي (Soft Start) المخصص لكل نمط حركة
    if current_direction != 'x':
        elapsed = utime.ticks_diff(utime.ticks_ms(), direction_start_time)
        if current_direction in ['a', 'd']:
            # تسارع هادئ وتدريجي للدوران خلال 1.5 ثانية (يبدأ بـ 15% إلى 30%)
            if elapsed < 1500:
                speed_val = 15.0 + (elapsed / 1500.0) * (max_target_speed - 15.0)
            else:
                speed_val = max_target_speed
        else:
            # تسارع هادئ جداً وبطيء للحركة المستقيمة خلال 2.5 ثانية (يبدأ بـ 10% إلى 25%)
            if elapsed < 2500:
                speed_val = 10.0 + (elapsed / 2500.0) * (max_target_speed - 10.0)
            else:
                speed_val = max_target_speed
        
        set_speed(speed_val)

    if utime.ticks_diff(utime.ticks_ms(), last_telemetry_time) > 500:
        try:
            dht_sensor.measure()
            temp, hum = dht_sensor.temperature(), dht_sensor.humidity()
        except:
            temp, hum = 0, 0
            
        mq9_val = int((adc_mq9.read_u16() / 65535) * 1000)
        mq135_val = int((adc_mq135.read_u16() / 65535) * 1000)
        distance_val = get_distance()
        battery_val = get_battery_voltage()
        gps_lat, gps_lng = parse_gps()
        
        avg_ticks_right = int((ticks_RR + ticks_FR) / 2)
        avg_ticks_left = int((ticks_FL + ticks_RL) / 2)
        
        telemetry_string = f"DATA:{temp},{hum},{mq9_val},{mq135_val},{distance_val},{gps_lat},{gps_lng},{avg_ticks_right},{avg_ticks_left},{battery_val}\n"
        uart.write(telemetry_string)
        
        last_telemetry_time = utime.ticks_ms()

    utime.sleep_us(100)