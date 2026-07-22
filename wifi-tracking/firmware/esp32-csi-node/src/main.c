/*
 * Nodo sensor CSI para seguimiento de presencia por WiFi.
 *
 * Se conecta a la WiFi de casa, hace ping al gateway a PING_HZ y captura
 * el CSI de las tramas recibidas. Cada medida se envia por UDP al servidor.
 *
 * Formato del paquete UDP (little-endian):
 *   uint16  magic      0xC51D
 *   uint8   version    1
 *   uint8   node_id
 *   uint32  seq
 *   int8    rssi
 *   uint8   channel
 *   uint16  csi_len    (bytes de datos CSI que siguen)
 *   int8[]  csi        (pares imag/real por subportadora)
 */

#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "nvs_flash.h"
#include "lwip/sockets.h"
#include "ping/ping_sock.h"

#ifndef WIFI_SSID
#define WIFI_SSID "MiWifi"
#endif
#ifndef WIFI_PASS
#define WIFI_PASS "password"
#endif
#ifndef NODE_ID
#define NODE_ID 1
#endif
#ifndef SERVER_IP
#define SERVER_IP "192.168.1.50"
#endif

#define SERVER_PORT 5566
#define PING_HZ 50
#define MAX_CSI_BYTES 512

static const char *TAG = "csi-node";

static int s_sock = -1;
static struct sockaddr_in s_server_addr;
static uint32_t s_seq = 0;
static volatile bool s_connected = false;

typedef struct __attribute__((packed)) {
    uint16_t magic;
    uint8_t version;
    uint8_t node_id;
    uint32_t seq;
    int8_t rssi;
    uint8_t channel;
    uint16_t csi_len;
} packet_header_t;

static void csi_rx_cb(void *ctx, wifi_csi_info_t *info)
{
    if (!info || !info->buf || info->len == 0 || s_sock < 0) {
        return;
    }

    static uint8_t buf[sizeof(packet_header_t) + MAX_CSI_BYTES];
    uint16_t csi_len = info->len > MAX_CSI_BYTES ? MAX_CSI_BYTES : info->len;

    packet_header_t *hdr = (packet_header_t *)buf;
    hdr->magic = 0xC51D;
    hdr->version = 1;
    hdr->node_id = NODE_ID;
    hdr->seq = s_seq++;
    hdr->rssi = info->rx_ctrl.rssi;
    hdr->channel = info->rx_ctrl.channel;
    hdr->csi_len = csi_len;
    memcpy(buf + sizeof(packet_header_t), info->buf, csi_len);

    sendto(s_sock, buf, sizeof(packet_header_t) + csi_len, 0,
           (struct sockaddr *)&s_server_addr, sizeof(s_server_addr));
}

static void start_csi(void)
{
    wifi_csi_config_t csi_config = {
        .lltf_en = true,
        .htltf_en = true,
        .stbc_htltf2_en = true,
        .ltf_merge_en = true,
        .channel_filter_en = true,
        .manu_scale = false,
        .shift = false,
    };
    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi_config));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(csi_rx_cb, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));
    ESP_LOGI(TAG, "CSI activado");
}

static void start_ping(uint32_t gateway_addr)
{
    esp_ping_config_t cfg = ESP_PING_DEFAULT_CONFIG();
    cfg.target_addr.u_addr.ip4.addr = gateway_addr;
    cfg.target_addr.type = ESP_IPADDR_TYPE_V4;
    cfg.interval_ms = 1000 / PING_HZ;
    cfg.count = ESP_PING_COUNT_INFINITE;
    cfg.task_stack_size = 3072;

    esp_ping_handle_t ping;
    ESP_ERROR_CHECK(esp_ping_new_session(&cfg, NULL, &ping));
    ESP_ERROR_CHECK(esp_ping_start(ping));
    ESP_LOGI(TAG, "Ping al gateway a %d Hz", PING_HZ);
}

static void on_wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        s_connected = false;
        ESP_LOGW(TAG, "Desconectado, reintentando...");
        vTaskDelay(pdMS_TO_TICKS(1000));
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *ev = (ip_event_got_ip_t *)data;
        ESP_LOGI(TAG, "IP: " IPSTR, IP2STR(&ev->ip_info.ip));
        s_connected = true;
        start_ping(ev->ip_info.gw.addr);
    }
}

void app_main(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t wifi_cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wifi_cfg));

    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_wifi_event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_wifi_event, NULL));

    wifi_config_t sta_cfg = {
        .sta = {
            .ssid = WIFI_SSID,
            .password = WIFI_PASS,
        },
    };
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &sta_cfg));
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    ESP_ERROR_CHECK(esp_wifi_start());

    s_sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    memset(&s_server_addr, 0, sizeof(s_server_addr));
    s_server_addr.sin_family = AF_INET;
    s_server_addr.sin_port = htons(SERVER_PORT);
    s_server_addr.sin_addr.s_addr = inet_addr(SERVER_IP);

    start_csi();

    while (true) {
        vTaskDelay(pdMS_TO_TICKS(10000));
        ESP_LOGI(TAG, "seq=%lu conectado=%d", (unsigned long)s_seq, s_connected);
    }
}
