/*
 * ARES RESCUE ROBOT - SECURE HEADLESS API & VISUAL CORE FIRMWARE
 * Monolithic Production-Ready Code for AI Thinker ESP32-CAM Board
 * 
 * Secure API Endpoints (Served via HTTPS on Port 443 with full CORS support):
 * - GET /stream            -> Raw low-latency MJPEG video stream (VGA, internal DRAM buffer)
 * - GET /toggle-lamp       -> Toggles GPIO 4 Searchlight (params: ?status=1/0 & optional ?brightness=0-255)
 * - GET /control-servo     -> Controls Pan/Tilt servos on GPIO 12 & 13 (params: ?axis=pan/tilt&angle=0-180)
 * - POST /save-wifi        -> Receives JSON or URL-encoded ssid & password, saves credentials, and reboots/connects
 * - GET /scan-wifi         -> Scans visible Wi-Fi networks and returns a clean JSON array
 * - Wildcard /webdav*      -> Full-featured WebDAV file system driver on port 443 mapping local micro SD card
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <Preferences.h>
#include <SD_MMC.h>
#include <esp_https_server.h> // Secure HTTP Server
#include <cctype>

// ==========================================
// EXPLICIT AI THINKER CAM PIN CONFIGURATION
// ==========================================
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

// ==========================================
// PIN DEFINITIONS FOR MECHANICAL SUBSYSTEM
// ==========================================
#define SERVO_PAN_PIN     12
#define SERVO_TILT_PIN    13
#define TACTICAL_LAMP_PIN  4

// Logging Macros
#define LOG_INF(format, ...) Serial.printf("[ARES-API-INFO] " format "\n", ##__VA_ARGS__)
#define LOG_WRN(format, ...) Serial.printf("[ARES-API-WARN] " format "\n", ##__VA_ARGS__)
#define LOG_ERR(format, ...) Serial.printf("[ARES-API-ERROR] " format "\n", ##__VA_ARGS__)

// Wi-Fi States
enum WifiState {
    WIFI_STATE_AP_ONLY,
    WIFI_STATE_CONNECTING,
    WIFI_STATE_STA_ONLY
};

WifiState wifi_state = WIFI_STATE_AP_ONLY;
unsigned long wifi_connect_start = 0;
bool trigger_connect = false;
httpd_handle_t server = NULL;

// Global settings
int current_pan = 90;
int current_tilt = 90;
int current_flash = 0;

// WebDAV boundary
#define PART_BOUNDARY "123456789000000000000987654321"

// ==========================================
// DEFAULT SELF-SIGNED SSL CERTIFICATE & KEY
// ==========================================
const char* default_servercert = R"rawliteral(
-----BEGIN CERTIFICATE-----
MIIDMDCCAhigAwIBAgIUBp0R8fJjpAeVEwr8pzrbQd/U5M4wDQYJKoZIhvcNAQEL
BQAwFjEUMBIGA1UEAwwLMTkyLjE2OC40LjEwHhcNMjYwNjE2MDg1NjU5WhcNMzYw
NjIzMDg1NjU5WjAWMRQwEgYDVQQDDAsxOTIuMTY4LjQuMTCCASIwDQYJKoZIhvcN
AQEBBQADggEPADCCAQoCggEBAMV8D2V305JyTn9usKTdzP1RWkVGDw0Dv8X8p3g9
GsDE53/HTa5MPxs6c9q/YZIz7eIGKBI/U1M4wLHao81MtUHlR507yloI6gk3geHv
PCMi4nD5GsbaP3gKC1IG4FNO+RkpiprhYOzf/7pLTtgl+IAKnaklKVNUIp1AwvSg
2xoRkPnWkV2mwDMtyM8mEPuLAFARZa7LaCBzrY1IeooqLavD+XLq7GVhyteLd9QO
OykVisR07ah4KaaUuQd8pj1pfnDOGP3NxwIblCljcCXqZUYOFwHzpYemIYTyJ06V
YjZ5fUwR2XNm0ltxd4hGbWLXnkVfF8rpUcr/rjl+HLUelfcCAwEAAaN2MHQwHQYD
VR0OBBYEFFb6Pi+m7382uZ9C+uf7U8had59UMB8GA1UdIwQYMBaAFFb6Pi+m7382
uZ9C+uf7U8had59UMA8GA1UdEwEB/wQFMAMBAf8wIQYDVR0RBBowGIcEwKgEAYcE
wKgBAYIKYXJlcy5sb2NhbDANBgkqhkiG9w0BAQsFAAOCAQEArCNEsIoFz6NcAYDu
ePCqkGX4+TEfBMKLiDC/uIfyaJ2/UTtICTVDKHn/5UQzh1Dn2XN5e57SqenFWKrD
EbvoFbjx0MNlcbD3q9YkvvZT8VLVi3MZ8oVcMWFnvOKtVyQX0FPXbH7biysQ0+vP
4rK49PWg+sfwpD7imMTAeitO7LDCavRcY0CJ47naAh1hiiLj2NaeEj0IF07m1yZn
FARGSvq1lZks0AQRXyOEb9s5LDcRDB7hmZdryGMEteIGzXnI5/JcnnqAcJXPNXms
pHUF0YhxpATGdd7UvZDepnV2AyIFIEL/Zp+nXRuxdC+MxM6+RBnuoDSEqrkibFyl
GzUqCg==
-----END CERTIFICATE-----
)rawliteral";

const char* default_prvtkey = R"rawliteral(
-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDFfA9ld9OSck5/
brCk3cz9UVpFRg8NA7/F/Kd4PRrAxOd/x02uTD8bOnPav2GSM+3iBigSP1NTOMCx
2qPNTLVB5UedO8paCOoJN4Hh7zwjIuJw+RrG2j94CgtSBuBTTvkZKYqa4WDs3/+6
S07YJfiACp2pJSlTVCKdQML0oNsaEZD51pFdpsAzLcjPJhD7iwBQEWWuy2ggc62N
SHqKKi2rw/ly6uxlYcrXi3fUDjspFYrEdO2oeCmmlLkHfKY9aX5wzhj9zccCG5Qp
Y3Al6mVGDhcB86WHpiGE8idOlWI2eX1MEdlzZtJbcXeIRm1i155FXxfK6VHK/645
fhy1HpX3AgMBAAECggEAA5B9fuLSYF0QZNJsseaBE8uHdWbdbo/SWYc9e4RkADmn
80+Vxh1MbZZENO/mEi1NaoO5G+b4WUeoqNSrIUJd8fsQUcfJm2HSoXRPUadJ8KRp
bcXfXa05PN3U1pgAWv6zQ3fia60bewsINZeWfwRdIzer88MTiRvoS8wTvIGK/EIV
UqjSBoN+7V7hMCXjCIx2dmVjLdmSrqqJBu88o+85fz1CIyKhpmDorUTpajl6Hb+w
mAl7fEb7ODbxAH65hDbZQ/iZhuk0yuhy0+ktW9kPdfR5QeO9TQv5YVmkA6NvxvBq
RpdBlTeKHACQqe93SPPfZVJEiHKtfKz3ijRjqV9sOQKBgQD9Y/hIzqgKNqDnb50u
Kue0JLPH4FepVXksZJxYiGGCkD0ZxEForASPEWdZNuChYJmfA/GF4sTcRIT1RPcB
0teo6YQQXU2zwRMPEOyciGmCLOj0doIXs5/lsTpKEs4hNjbOmtgK5TYK/cBozYqA
NFpQsgtUW/9N37u2EEX+NSi8LQKBgQDHhLOtuFvHM6brvh6l3k4Wzsht3M1hhw1C
bC05ZOvDLr1HgR+2wktzFpKz01UEcTtxSqmFtz0+3a3iDaqYxKyhS6mlvVRISmBU
SPQ6f6lKevFw3HmB8iYr6D+IK7dxESAIuNAN4IF1XYuwZty2B/U9OcBCghd9jBhS
A8f0AXAdMwKBgCbyK6I9KTTQqrCHxjfnXk+g6IULJU4glgxNtn4hECO6ObnxIUCO
V/EJcsISnjoPl+0J9SBn92wHmAv+upxsJLuQkLzXKm87eMtzBXsVuGnKr0+Lu3kb
IbNzJwtlkosmQwxEXnpmOoU79Uvmc6g647rNctJXhYkZn0dffvKQhx9NAoGBAI4O
V/hKmV4d0q1q8ltbCvKGTIKcgcb8513xs8l3p72S28W7lB8F+753xgAvagr9rDsf
08+XBg5qu9GFtX+MGPXG74VIZmgKPMgGIY49MwYKvzmCYSk6hh8g/4suxS/F568O
F2SqAsLT1g/FTUR2KhBrvA4enicPxokulAGRvIetAoGBAO0GmrVJBIvWaYn1VurO
fRwdQ/7H6FExvHIW8CKehz6FgrazjI6eJHEvYDQjGHdZmKsLzNvlniWc+d07RjSN
g9S8wbTx4BXOlKXKd2xLE7pSkCs65M4EuLwIBN9ktEvvpyxsu8EPa2H0+2Jr5lAE
nN/R03F24uemBiu94Sqq66Fc
-----END PRIVATE KEY-----
)rawliteral";

uint8_t* servercert_buf = NULL;
size_t servercert_len = 0;
uint8_t* prvtkey_buf = NULL;
size_t prvtkey_len = 0;

void load_certificates() {
    File certFile = SD_MMC.open("/servercert.pem", FILE_READ);
    File keyFile = SD_MMC.open("/prvtkey.pem", FILE_READ);
    
    if (certFile && keyFile && certFile.size() > 0 && keyFile.size() > 0) {
        LOG_INF("Loading custom SSL certificates from SD card...");
        
        servercert_len = certFile.size();
        servercert_buf = (uint8_t*)malloc(servercert_len + 1);
        certFile.read(servercert_buf, servercert_len);
        servercert_buf[servercert_len] = '\0';
        servercert_len++; // count null terminator
        
        prvtkey_len = keyFile.size();
        prvtkey_buf = (uint8_t*)malloc(prvtkey_len + 1);
        keyFile.read(prvtkey_buf, prvtkey_len);
        prvtkey_buf[prvtkey_len] = '\0';
        prvtkey_len++; // count null terminator
        
        certFile.close();
        keyFile.close();
    } else {
        LOG_WRN("Custom certificates not found on SD. Using built-in self-signed certificate.");
        if (certFile) certFile.close();
        if (keyFile) keyFile.close();
        
        servercert_len = strlen(default_servercert) + 1;
        servercert_buf = (uint8_t*)default_servercert;
        
        prvtkey_len = strlen(default_prvtkey) + 1;
        prvtkey_buf = (uint8_t*)default_prvtkey;
    }
}

// ==========================================
// HELPER UTILITIES
// ==========================================

void url_decode(char *dst, const char *src) {
    char a, b;
    while (*src) {
        if ((*src == '%') &&
            ((a = src[1]) && (b = src[2])) &&
            (isxdigit(a) && isxdigit(b))) {
            if (a >= 'a') a -= 'a' - 'A';
            if (a >= 'A') a -= 'A' - 10;
            else a -= '0';
            if (b >= 'a') b -= 'a' - 'A';
            if (b >= 'A') b -= 'A' - 10;
            else b -= '0';
            *dst++ = 16 * a + b;
            src += 3;
        } else if (*src == '+') {
            *dst++ = ' ';
            src++;
        } else {
            *dst++ = *src++;
        }
    }
    *dst = '\0';
}

void save_wifi_creds(const String& ssid, const String& pass) {
    Preferences prefs;
    prefs.begin("ares", false);
    prefs.putString("ssid", ssid);
    prefs.putString("pass", pass);
    prefs.end();
}

void load_wifi_creds(String& ssid, String& pass) {
    Preferences prefs;
    prefs.begin("ares", true);
    ssid = prefs.getString("ssid", "");
    pass = prefs.getString("pass", "");
    prefs.end();
}

void save_servo_positions(int pan, int tilt) {
    Preferences prefs;
    prefs.begin("ares", false);
    prefs.putInt("pan", pan);
    prefs.putInt("tilt", tilt);
    prefs.end();
}

void load_servo_positions(int& pan, int& tilt) {
    Preferences prefs;
    prefs.begin("ares", true);
    pan = prefs.getInt("pan", 90);
    tilt = prefs.getInt("tilt", 90);
    prefs.end();
}

void save_flash_state(int val) {
    Preferences prefs;
    prefs.begin("ares", false);
    prefs.putInt("flash", val);
    prefs.end();
}

void load_flash_state(int& val) {
    Preferences prefs;
    prefs.begin("ares", true);
    val = prefs.getInt("flash", 0);
    prefs.end();
}

// Servo Control function
void set_servo_angle(uint8_t pin, int angle) {
    angle = constrain(angle, 0, 180);
    // Map angle (0-180) to pulse width (544-2400 microseconds)
    int pulse_width = map(angle, 0, 180, 544, 2400);
    // Convert pulse width to 12-bit duty cycle at 50Hz (Period = 20000us)
    // Duty = (pulse_width * 4096) / 20000
    int duty = (pulse_width * 4096) / 20000;
    ledcWrite(pin, duty);
}

// ==========================================
// HARDWARE INITIALIZATION
// ==========================================

bool init_sd_card() {
    // Enable 1-bit mode to free GPIO 4 (Flash Lamp) and GPIO 12/13 (Servos)
    if (!SD_MMC.begin("/sdcard", true)) {
        LOG_ERR("SD_MMC Card Mount Failed. WebDAV will serve blank root.");
        return false;
    }
    LOG_INF("SD_MMC mounted successfully.");
    return true;
}

bool init_camera() {
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
    
    // Core parameters: VGA inside DRAM, fb_count = 1, jpeg_quality = 12
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 12;
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_DRAM;
    config.grab_mode = CAMERA_GRAB_LATEST;

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        LOG_ERR("Camera initialization failed: 0x%x", err);
        return false;
    }

    sensor_t * s = esp_camera_sensor_get();
    if (s) {
        s->set_vflip(s, 1);    // Vertically flip feed for robotics mount
        s->set_hmirror(s, 1);  // Horizontally mirror feed
    }

    LOG_INF("Camera initialized successfully.");
    return true;
}

// ==========================================
// WEBDAV PROTOCOL HANDLER
// ==========================================

void send_chunk(httpd_req_t* req, const char* str) {
    if (str) {
        httpd_resp_send_chunk(req, str, strlen(str));
    } else {
        httpd_resp_send_chunk(req, NULL, 0);
    }
}

void send_prop_response(httpd_req_t *req, const char *href_path, bool is_dir, size_t size, time_t mtime, const char *display_name) {
    char chunk[512];
    char mtime_str[64] = "Thu, 01 Jan 1970 00:00:00 GMT";
    if (mtime > 0) {
        struct tm *tm_info = gmtime(&mtime);
        strftime(mtime_str, sizeof(mtime_str), "%a, %d %b %Y %H:%M:%S GMT", tm_info);
    }
    
    if (!display_name || strlen(display_name) == 0) {
        display_name = "/";
    }

    snprintf(chunk, sizeof(chunk),
        "<D:response xmlns:D=\"DAV:\">"
        "<D:href>/webdav%s</D:href>"
        "<D:propstat>"
        "<D:status>HTTP/1.1 200 OK</D:status>"
        "<D:prop>"
        "<D:getlastmodified>%s</D:getlastmodified>"
        "<D:creationdate>%s</D:creationdate>",
        href_path, mtime_str, mtime_str);
    send_chunk(req, chunk);
    
    if (is_dir) {
        send_chunk(req, "<D:resourcetype><D:collection/></D:resourcetype>");
    } else {
        snprintf(chunk, sizeof(chunk),
            "<D:getcontentlength>%u</D:getcontentlength>"
            "<D:getcontenttype>application/octet-stream</D:getcontenttype>"
            "<D:resourcetype/>",
            size);
        send_chunk(req, chunk);
    }
    
    snprintf(chunk, sizeof(chunk),
        "<D:displayname>%s</D:displayname>"
        "</D:prop>"
        "</D:propstat>"
        "</D:response>",
        display_name);
    send_chunk(req, chunk);
}

esp_err_t webdav_handler(httpd_req_t *req) {
    char path[256];
    const char *uri = req->uri;
    
    if (strncmp(uri, "/webdav", 7) == 0) {
        snprintf(path, sizeof(path), "%s", uri + 7);
    } else {
        snprintf(path, sizeof(path), "%s", uri);
    }
    
    if (path[0] == '\0') {
        strcpy(path, "/");
    }
    
    size_t len = strlen(path);
    if (len > 1 && path[len - 1] == '/') {
        path[len - 1] = '\0';
    }
    
    char decoded_path[256];
    url_decode(decoded_path, path);
    
    // Set response headers required for WebDAV + CORS
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    httpd_resp_set_hdr(req, "DAV", "1");
    httpd_resp_set_hdr(req, "Allow", "PROPPATCH,PROPFIND,OPTIONS,DELETE,MOVE,COPY,HEAD,POST,PUT,GET");
    
    if (req->method == HTTP_OPTIONS) {
        httpd_resp_send(req, NULL, 0);
        return ESP_OK;
    }
    
    if (req->method == HTTP_LOCK) {
        const char* lockToken = "opaquelocktoken:01234567-89ab-cdef-0123-456789abcdef";
        httpd_resp_set_hdr(req, "Lock-Token", lockToken);
        httpd_resp_set_type(req, "application/xml;charset=utf-8");
        char resp[512];
        snprintf(resp, sizeof(resp),
            "<?xml version=\"1.0\" encoding=\"utf-8\"?>"
            "<D:prop xmlns:D=\"DAV:\">"
            "<D:lockdiscovery>"
            "<D:activelock>"
            "<D:locktype><D:write/></D:locktype>"
            "<D:lockscope><D:exclusive/></D:lockscope>"
            "<D:depth>Infinity</D:depth>"
            "<D:owner><D:href>ARES</D:href></D:owner>"
            "<D:timeout>Second-3600</D:timeout>"
            "<D:locktoken><D:href>%s</D:href></D:locktoken>"
            "</D:activelock>"
            "</D:lockdiscovery>"
            "</D:prop>",
            lockToken);
        httpd_resp_sendstr(req, resp);
        return ESP_OK;
    }
    
    if (req->method == HTTP_UNLOCK) {
        httpd_resp_set_status(req, "204 No Content");
        httpd_resp_send(req, NULL, 0);
        return ESP_OK;
    }
    
    if (req->method == HTTP_PROPFIND || req->method == HTTP_PROPPATCH) {
        char depth_val[16] = "0";
        httpd_req_get_hdr_value_str(req, "Depth", depth_val, sizeof(depth_val));
        bool depth_is_1 = (strcmp(depth_val, "1") == 0);
        
        if (strcmp(decoded_path, "/") != 0 && !SD_MMC.exists(decoded_path)) {
            httpd_resp_send_404(req);
            return ESP_OK;
        }
        
        File root = SD_MMC.open(decoded_path);
        if (!root) {
            httpd_resp_send_404(req);
            return ESP_OK;
        }
        
        bool root_is_dir = root.isDirectory();
        size_t root_size = root_is_dir ? 0 : root.size();
        time_t root_mtime = root.getLastWrite();
        const char *root_name = root.name();
        
        const char* last_slash = strrchr(root_name, '/');
        if (last_slash) {
            root_name = last_slash + 1;
        }
        if (strcmp(decoded_path, "/") == 0) {
            root_name = "";
        }
        
        httpd_resp_set_status(req, "207 Multi-Status");
        httpd_resp_set_type(req, "application/xml;charset=utf-8");
        send_chunk(req, "<?xml version=\"1.0\" encoding=\"utf-8\"?><D:multistatus xmlns:D=\"DAV:\">");
        
        send_prop_response(req, decoded_path, root_is_dir, root_size, root_mtime, root_name);
        
        if (depth_is_1 && root_is_dir) {
            File child = root.openNextFile();
            while (child) {
                char child_path[256];
                const char* cname = child.name();
                const char* c_last_slash = strrchr(cname, '/');
                if (c_last_slash) {
                    cname = c_last_slash + 1;
                }
                
                if (strcmp(decoded_path, "/") == 0) {
                    snprintf(child_path, sizeof(child_path), "/%s", cname);
                } else {
                    snprintf(child_path, sizeof(child_path), "%s/%s", decoded_path, cname);
                }
                
                send_prop_response(req, child_path, child.isDirectory(), child.size(), child.getLastWrite(), cname);
                child.close();
                child = root.openNextFile();
            }
        }
        root.close();
        
        send_chunk(req, "</D:multistatus>");
        send_chunk(req, NULL);
        return ESP_OK;
    }
    
    if (req->method == HTTP_GET || req->method == HTTP_HEAD) {
        File file = SD_MMC.open(decoded_path, FILE_READ);
        if (!file || file.isDirectory()) {
            if (file) file.close();
            httpd_resp_send_404(req);
            return ESP_OK;
        }
        
        char size_str[32];
        sprintf(size_str, "%u", file.size());
        httpd_resp_set_hdr(req, "Content-Length", size_str);
        
        if (req->method == HTTP_HEAD) {
            file.close();
            httpd_resp_send(req, NULL, 0);
            return ESP_OK;
        }
        
        httpd_resp_set_type(req, "application/octet-stream");
        
        char *buffer = (char *)malloc(4096);
        if (!buffer) {
            file.close();
            httpd_resp_send_500(req);
            return ESP_OK;
        }
        
        size_t read_bytes;
        while ((read_bytes = file.read((uint8_t *)buffer, 4096)) > 0) {
            if (httpd_resp_send_chunk(req, buffer, read_bytes) != ESP_OK) {
                break;
            }
        }
        free(buffer);
        file.close();
        httpd_resp_send_chunk(req, NULL, 0);
        return ESP_OK;
    }
    
    if (req->method == HTTP_PUT) {
        File file = SD_MMC.open(decoded_path, FILE_WRITE);
        if (!file) {
            httpd_resp_send_500(req);
            return ESP_OK;
        }
        
        size_t remaining = req->content_len;
        char *buffer = (char *)malloc(4096);
        if (!buffer) {
            file.close();
            httpd_resp_send_500(req);
            return ESP_OK;
        }
        
        int received;
        while (remaining > 0) {
            size_t to_recv = (remaining < 4096) ? remaining : 4096;
            received = httpd_req_recv(req, buffer, to_recv);
            if (received <= 0) {
                if (received == HTTPD_SOCK_ERR_TIMEOUT) {
                    continue;
                }
                break;
            }
            file.write((uint8_t *)buffer, received);
            remaining -= received;
        }
        free(buffer);
        file.close();
        
        httpd_resp_set_status(req, "201 Created");
        httpd_resp_send(req, NULL, 0);
        return ESP_OK;
    }
    
    if (req->method == HTTP_DELETE) {
        if (strcmp(decoded_path, "/") == 0) {
            httpd_resp_send_err(req, HTTPD_403_FORBIDDEN, "Cannot delete root");
            return ESP_OK;
        }
        
        if (!SD_MMC.exists(decoded_path)) {
            httpd_resp_send_404(req);
            return ESP_OK;
        }
        
        File file = SD_MMC.open(decoded_path);
        bool is_dir = file.isDirectory();
        file.close();
        
        bool res;
        if (is_dir) {
            res = SD_MMC.rmdir(decoded_path);
        } else {
            res = SD_MMC.remove(decoded_path);
        }
        
        if (res) {
            httpd_resp_send(req, NULL, 0);
        } else {
            httpd_resp_send_500(req);
        }
        return ESP_OK;
    }
    
    if (req->method == HTTP_MKCOL) {
        if (SD_MMC.exists(decoded_path)) {
            httpd_resp_set_status(req, "405 Method Not Allowed");
            httpd_resp_send(req, NULL, 0);
            return ESP_OK;
        }
        
        bool res = SD_MMC.mkdir(decoded_path);
        if (res) {
            httpd_resp_set_status(req, "201 Created");
            httpd_resp_send(req, NULL, 0);
        } else {
            httpd_resp_send_500(req);
        }
        return ESP_OK;
    }
    
    if (req->method == HTTP_MOVE) {
        char dest_val[256] = "";
        httpd_req_get_hdr_value_str(req, "Destination", dest_val, sizeof(dest_val));
        
        const char *pos = strstr(dest_val, "/webdav");
        if (!pos) {
            httpd_resp_send_404(req);
            return ESP_OK;
        }
        pos += 7; // skip "/webdav"
        
        char dest_path[256];
        url_decode(dest_path, pos);
        
        size_t dlen = strlen(dest_path);
        if (dlen > 1 && dest_path[dlen - 1] == '/') {
            dest_path[dlen - 1] = '\0';
        }
        
        bool res = SD_MMC.rename(decoded_path, dest_path);
        if (res) {
            httpd_resp_set_status(req, "201 Created");
            httpd_resp_send(req, NULL, 0);
        } else {
            httpd_resp_send_500(req);
        }
        return ESP_OK;
    }
    
    httpd_resp_send_err(req, HTTPD_404_NOT_FOUND, "Not implemented");
    return ESP_OK;
}

// ==========================================
// HTTP ENDPOINTS (RAW DATA / JSON ONLY)
// ==========================================

esp_err_t stream_handler(httpd_req_t *req) {
    if (req->method == HTTP_OPTIONS) {
        httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
        httpd_resp_set_hdr(req, "Access-Control-Allow-Methods", "GET, OPTIONS");
        httpd_resp_set_hdr(req, "Access-Control-Allow-Headers", "Content-Type");
        httpd_resp_send(req, NULL, 0);
        return ESP_OK;
    }

    camera_fb_t * fb = NULL;
    esp_err_t res = ESP_OK;
    size_t _jpg_buf_len = 0;
    uint8_t * _jpg_buf = NULL;
    char part_buf[64];

    static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
    static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
    static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

    res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
    if (res != ESP_OK) {
        return res;
    }

    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

    while (true) {
        fb = esp_camera_fb_get();
        if (!fb) {
            LOG_ERR("Camera capture failed");
            res = ESP_FAIL;
        } else {
            _jpg_buf_len = fb->len;
            _jpg_buf = fb->buf;
        }

        if (res == ESP_OK) {
            size_t hlen = snprintf(part_buf, 64, _STREAM_PART, _jpg_buf_len);
            res = httpd_resp_send_chunk(req, part_buf, hlen);
        }
        if (res == ESP_OK) {
            res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
        }
        if (res == ESP_OK) {
            res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
        }
        if (fb) {
            esp_camera_fb_return(fb);
            fb = NULL;
            _jpg_buf = NULL;
        } else if (res == ESP_OK) {
            break;
        }

        if (res != ESP_OK) {
            break;
        }
        
        vTaskDelay(10 / portTICK_PERIOD_MS);
    }
    return res;
}

esp_err_t toggle_lamp_handler(httpd_req_t *req) {
    if (req->method == HTTP_OPTIONS) {
        httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
        httpd_resp_set_hdr(req, "Access-Control-Allow-Methods", "GET, OPTIONS");
        httpd_resp_set_hdr(req, "Access-Control-Allow-Headers", "Content-Type");
        httpd_resp_send(req, NULL, 0);
        return ESP_OK;
    }

    char buf[128];
    int intensity = 0;
    if (httpd_req_get_url_query_str(req, buf, sizeof(buf)) == ESP_OK) {
        char param[32];
        if (httpd_query_key_value(buf, "status", param, sizeof(param)) == ESP_OK) {
            int status = atoi(param);
            intensity = (status == 1) ? 128 : 0;
        }
        if (httpd_query_key_value(buf, "brightness", param, sizeof(param)) == ESP_OK) {
            intensity = atoi(param);
        }
    }
    
    current_flash = intensity;
    ledcWrite(TACTICAL_LAMP_PIN, intensity);
    save_flash_state(intensity);
    
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    httpd_resp_set_type(req, "application/json");
    
    char resp[128];
    snprintf(resp, sizeof(resp), "{\"status\":\"success\",\"intensity\":%d}", intensity);
    httpd_resp_send(req, resp, -1);
    return ESP_OK;
}

esp_err_t control_servo_handler(httpd_req_t *req) {
    if (req->method == HTTP_OPTIONS) {
        httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
        httpd_resp_set_hdr(req, "Access-Control-Allow-Methods", "GET, OPTIONS");
        httpd_resp_set_hdr(req, "Access-Control-Allow-Headers", "Content-Type");
        httpd_resp_send(req, NULL, 0);
        return ESP_OK;
    }

    char buf[128];
    char axis[32] = "";
    int angle = -1;
    
    if (httpd_req_get_url_query_str(req, buf, sizeof(buf)) == ESP_OK) {
        httpd_query_key_value(buf, "axis", axis, sizeof(axis));
        char param[32];
        if (httpd_query_key_value(buf, "angle", param, sizeof(param)) == ESP_OK) {
            angle = atoi(param);
        }
    }
    
    bool success = false;
    if (angle >= 0 && angle <= 180) {
        if (strcmp(axis, "pan") == 0) {
            current_pan = angle;
            set_servo_angle(SERVO_PAN_PIN, angle);
            save_servo_positions(current_pan, current_tilt);
            success = true;
            LOG_INF("Pan Servo set to %d", angle);
        } else if (strcmp(axis, "tilt") == 0) {
            current_tilt = angle;
            set_servo_angle(SERVO_TILT_PIN, angle);
            save_servo_positions(current_pan, current_tilt);
            success = true;
            LOG_INF("Tilt Servo set to %d", angle);
        }
    }
    
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    httpd_resp_set_type(req, "application/json");
    
    char resp[128];
    if (success) {
        snprintf(resp, sizeof(resp), "{\"status\":\"success\",\"axis\":\"%s\",\"angle\":%d}", axis, angle);
    } else {
        snprintf(resp, sizeof(resp), "{\"status\":\"error\",\"message\":\"Invalid axis or angle (%d)\"}", angle);
    }
    httpd_resp_send(req, resp, -1);
    return ESP_OK;
}

esp_err_t save_wifi_handler(httpd_req_t *req) {
    if (req->method == HTTP_OPTIONS) {
        httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
        httpd_resp_set_hdr(req, "Access-Control-Allow-Methods", "POST, OPTIONS");
        httpd_resp_set_hdr(req, "Access-Control-Allow-Headers", "Content-Type");
        httpd_resp_send(req, NULL, 0);
        return ESP_OK;
    }
    
    char content[128] = "";
    size_t recv_size = (req->content_len < sizeof(content) - 1) ? req->content_len : sizeof(content) - 1;
    if (recv_size > 0) {
        int ret = httpd_req_recv(req, content, recv_size);
        if (ret > 0) {
            content[ret] = '\0';
            LOG_INF("Received Wi-Fi config payload: %s", content);
            
            char ssid[64] = "";
            char pass[64] = "";
            
            // Try parsing as JSON first
            char *ssid_ptr = strstr(content, "\"ssid\"");
            char *pass_ptr = strstr(content, "\"password\"");
            if (!pass_ptr) pass_ptr = strstr(content, "\"pass\"");
            
            if (ssid_ptr && pass_ptr) {
                char *s_start = strchr(ssid_ptr, ':');
                if (s_start) {
                    s_start = strchr(s_start, '\"');
                    if (s_start) {
                        s_start++;
                        char *s_end = strchr(s_start, '\"');
                        if (s_end) {
                            int slen = s_end - s_start;
                            if (slen < 64) {
                                strncpy(ssid, s_start, slen);
                                ssid[slen] = '\0';
                            }
                        }
                    }
                }
                char *p_start = strchr(pass_ptr, ':');
                if (p_start) {
                    p_start = strchr(p_start, '\"');
                    if (p_start) {
                        p_start++;
                        char *p_end = strchr(p_start, '\"');
                        if (p_end) {
                            int plen = p_end - p_start;
                            if (plen < 64) {
                                strncpy(pass, p_start, plen);
                                pass[plen] = '\0';
                            }
                        }
                    }
                }
            } else {
                // Parse as URL-encoded
                char *tok = strtok(content, "&");
                while (tok != NULL) {
                    char *eq = strchr(tok, '=');
                    if (eq) {
                        *eq = '\0';
                        char *val = eq + 1;
                        if (strcmp(tok, "ssid") == 0) {
                            url_decode(ssid, val);
                        } else if (strcmp(tok, "pass") == 0 || strcmp(tok, "password") == 0) {
                            url_decode(pass, val);
                        }
                    }
                    tok = strtok(NULL, "&");
                }
            }
            
            if (strlen(ssid) > 0) {
                save_wifi_creds(String(ssid), String(pass));
                LOG_INF("Credentials updated from API. Target SSID: %s", ssid);
                trigger_connect = true;
            }
        }
    }
    
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, "{\"status\":\"success\",\"message\":\"Wi-Fi credentials saved. Initializing link connection.\"}", -1);
    return ESP_OK;
}

esp_err_t scan_wifi_handler(httpd_req_t *req) {
    if (req->method == HTTP_OPTIONS) {
        httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
        httpd_resp_set_hdr(req, "Access-Control-Allow-Methods", "GET, OPTIONS");
        httpd_resp_set_hdr(req, "Access-Control-Allow-Headers", "Content-Type");
        httpd_resp_send(req, NULL, 0);
        return ESP_OK;
    }
    
    LOG_INF("Scanning visible Wi-Fi networks...");
    int n = WiFi.scanNetworks();
    String json = "{\"networks\":[";
    for (int i = 0; i < n; ++i) {
        if (i > 0) json += ",";
        json += "{\"ssid\":\"" + WiFi.SSID(i) + "\",\"rssi\":" + String(WiFi.RSSI(i)) + "}";
    }
    json += "]}";
    
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, json.c_str(), json.length());
    return ESP_OK;
}

// ==========================================
// HTTPS SERVER ORCHESTRATION
// ==========================================

void start_web_server() {
    load_certificates();
    
    httpd_ssl_config_t config = HTTPD_SSL_CONFIG_DEFAULT();
    config.cacert_pem = servercert_buf;
    config.cacert_len = servercert_len;
    config.prvtkey_pem = prvtkey_buf;
    config.prvtkey_len = prvtkey_len;
    
    config.httpd.uri_match_fn = httpd_uri_match_wildcard;
    config.port_secure = 443;
    
    // Safety sockets bounds to preserve limited heap RAM
    config.httpd.max_open_sockets = 2;
    config.httpd.lru_purge_enable = true;
    
    LOG_INF("Starting secure HTTPS server on port 443...");
    if (httpd_ssl_start(&server, &config) == ESP_OK) {
        
        // Low-latency MJPEG Stream
        httpd_uri_t stream_uri = {
            .uri = "/stream", .method = HTTP_GET, .handler = stream_handler, .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &stream_uri);
        
        // Searchlight status controller
        httpd_uri_t toggle_lamp_uri = {
            .uri = "/toggle-lamp", .method = HTTP_GET, .handler = toggle_lamp_handler, .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &toggle_lamp_uri);
        
        httpd_uri_t toggle_lamp_options = {
            .uri = "/toggle-lamp", .method = HTTP_OPTIONS, .handler = toggle_lamp_handler, .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &toggle_lamp_options);
        
        // Servo axis angle controller
        httpd_uri_t control_servo_uri = {
            .uri = "/control-servo", .method = HTTP_GET, .handler = control_servo_handler, .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &control_servo_uri);
        
        httpd_uri_t control_servo_options = {
            .uri = "/control-servo", .method = HTTP_OPTIONS, .handler = control_servo_handler, .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &control_servo_options);
        
        // WiFi Connection target saves
        httpd_uri_t save_wifi_uri = {
            .uri = "/save-wifi", .method = HTTP_POST, .handler = save_wifi_handler, .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &save_wifi_uri);
        
        httpd_uri_t save_wifi_options = {
            .uri = "/save-wifi", .method = HTTP_OPTIONS, .handler = save_wifi_handler, .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &save_wifi_options);
        
        // Network list scanner
        httpd_uri_t scan_wifi_uri = {
            .uri = "/scan-wifi", .method = HTTP_GET, .handler = scan_wifi_handler, .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &scan_wifi_uri);
        
        httpd_uri_t scan_wifi_options = {
            .uri = "/scan-wifi", .method = HTTP_OPTIONS, .handler = scan_wifi_handler, .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &scan_wifi_options);
        
        // WebDAV mount path routers
        static const httpd_uri_t webdav_uri_options = {
            .uri = "/webdav*", .method = HTTP_OPTIONS, .handler = webdav_handler, .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &webdav_uri_options);
        
        static const httpd_uri_t webdav_uri_propfind = {
            .uri = "/webdav*", .method = HTTP_PROPFIND, .handler = webdav_handler, .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &webdav_uri_propfind);
        
        static const httpd_uri_t webdav_uri_proppatch = {
            .uri = "/webdav*", .method = HTTP_PROPPATCH, .handler = webdav_handler, .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &webdav_uri_proppatch);
        
        static const httpd_uri_t webdav_uri_get = {
            .uri = "/webdav*", .method = HTTP_GET, .handler = webdav_handler, .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &webdav_uri_get);
        
        static const httpd_uri_t webdav_uri_head = {
            .uri = "/webdav*", .method = HTTP_HEAD, .handler = webdav_handler, .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &webdav_uri_head);
        
        static const httpd_uri_t webdav_uri_put = {
            .uri = "/webdav*", .method = HTTP_PUT, .handler = webdav_handler, .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &webdav_uri_put);
        
        static const httpd_uri_t webdav_uri_delete = {
            .uri = "/webdav*", .method = HTTP_DELETE, .handler = webdav_handler, .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &webdav_uri_delete);
        
        static const httpd_uri_t webdav_uri_mkcol = {
            .uri = "/webdav*", .method = HTTP_MKCOL, .handler = webdav_handler, .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &webdav_uri_mkcol);
        
        static const httpd_uri_t webdav_uri_move = {
            .uri = "/webdav*", .method = HTTP_MOVE, .handler = webdav_handler, .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &webdav_uri_move);
        
        static const httpd_uri_t webdav_uri_lock = {
            .uri = "/webdav*", .method = HTTP_LOCK, .handler = webdav_handler, .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &webdav_uri_lock);
        
        static const httpd_uri_t webdav_uri_unlock = {
            .uri = "/webdav*", .method = HTTP_UNLOCK, .handler = webdav_handler, .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &webdav_uri_unlock);
        
        LOG_INF("Secure HTTPS server is running and listening.");
    } else {
        LOG_ERR("Could not initialize secure HTTPS server.");
    }
}

// ==========================================
// MAIN ARDUINO LOOP & SETUP
// ==========================================

void setup() {
    Serial.begin(115200);
    delay(1000);
    LOG_INF("Booting Headless Secure ARES Mission Visual Core Subsystem...");
    
    // Read stored settings from Preferences
    load_servo_positions(current_pan, current_tilt);
    load_flash_state(current_flash);
    
    // Initialize PWM Pins for Servos (50Hz)
    ledcAttach(SERVO_PAN_PIN, 50, 12);
    set_servo_angle(SERVO_PAN_PIN, current_pan);
    ledcAttach(SERVO_TILT_PIN, 50, 12);
    set_servo_angle(SERVO_TILT_PIN, current_tilt);
    
    // Initialize PWM Pin for searchlight (5kHz, 8-bit)
    pinMode(TACTICAL_LAMP_PIN, OUTPUT);
    ledcAttach(TACTICAL_LAMP_PIN, 5000, 8);
    ledcWrite(TACTICAL_LAMP_PIN, current_flash);
    
    // Initialize hardware peripherals
    init_sd_card();
    init_camera();
    
    // Initialize Wi-Fi: always boot into AP Mode first
    WiFi.softAP("ARES-CAMERA", "ARES2026");
    wifi_state = WIFI_STATE_AP_ONLY;
    LOG_INF("AP Mode Started: SSID = ARES-CAMERA, IP = 192.168.4.1");
    
    // If credentials exist, prepare auto fallback connecting task
    String saved_ssid, saved_pass;
    load_wifi_creds(saved_ssid, saved_pass);
    if (saved_ssid.length() > 0) {
        LOG_INF("Saved station credentials found. Attempting link connection...");
        WiFi.mode(WIFI_AP_STA);
        WiFi.begin(saved_ssid.c_str(), saved_pass.c_str());
        wifi_state = WIFI_STATE_CONNECTING;
        wifi_connect_start = millis();
    }
    
    // Fire up Secure API server
    start_web_server();
}

void loop() {
    // Wi-Fi Connection State Machine & Watchdog
    if (wifi_state == WIFI_STATE_CONNECTING) {
        if (WiFi.status() == WL_CONNECTED) {
            WiFi.mode(WIFI_STA);
            wifi_state = WIFI_STATE_STA_ONLY;
            LOG_INF("Connected to Router! STA mode active. Device IP = %s", WiFi.localIP().toString().c_str());
        } else if (millis() - wifi_connect_start > 45000) {
            LOG_WRN("Failed to establish Wi-Fi link. Reverting back to standalone Access Point.");
            WiFi.disconnect(true);
            WiFi.mode(WIFI_AP);
            WiFi.softAP("ARES-CAMERA", "ARES2026");
            wifi_state = WIFI_STATE_AP_ONLY;
        }
    } else if (wifi_state == WIFI_STATE_STA_ONLY) {
        if (WiFi.status() != WL_CONNECTED) {
            LOG_ERR("Router connection lost! Recovering communication line by starting Access Point.");
            WiFi.disconnect(true);
            WiFi.mode(WIFI_AP);
            WiFi.softAP("ARES-CAMERA", "ARES2026");
            wifi_state = WIFI_STATE_AP_ONLY;
        }
    }
    
    // UI Trigger
    if (trigger_connect) {
        trigger_connect = false;
        String saved_ssid, saved_pass;
        load_wifi_creds(saved_ssid, saved_pass);
        if (saved_ssid.length() > 0) {
            LOG_INF("Initiating manual connection sequence to %s...", saved_ssid.c_str());
            WiFi.mode(WIFI_AP_STA);
            WiFi.softAP("ARES-CAMERA", "ARES2026");
            WiFi.begin(saved_ssid.c_str(), saved_pass.c_str());
            wifi_state = WIFI_STATE_CONNECTING;
            wifi_connect_start = millis();
        }
    }
    
    delay(100);
}
