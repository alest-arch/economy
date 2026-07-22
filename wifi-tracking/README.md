# WiFi Person Tracking — sensado de presencia device-free

Proyecto experimental **sin ánimo de lucro** para detectar en qué habitación de
tu casa hay personas usando únicamente la señal WiFi — **sin cámaras, sin
móviles, sin wearables**. Funciona con la técnica **CSI (Channel State
Information)**: un cuerpo humano moviéndose altera el multipath de la señal
WiFi, y esa distorsión se puede medir y clasificar.

> ⚠️ **Uso responsable**: úsalo solo en tu propia casa e informa a las personas
> que viven contigo. Detectar la presencia de personas sin su conocimiento
> puede ser ilegal en tu país (en España/UE aplica el RGPD incluso en contextos
> domésticos si afecta a terceros).

## Cómo funciona

```
[ESP32 salón] ──┐
[ESP32 cocina]──┤  CSI por UDP   ┌──────────────┐   WebSocket   ┌───────────┐
[ESP32 dorm-1]──┼───────────────>│ servidor     │──────────────>│ dashboard │
[ESP32 dorm-2]──┘                │ Python       │               │ navegador │
                                 └──────────────┘               └───────────┘
```

1. Cada **ESP32** (~5 €) se conecta a tu WiFi y hace ping al router 50 veces
   por segundo. De cada respuesta captura el CSI (amplitud/fase de 64
   subportadoras) y lo manda por UDP al servidor.
2. El **servidor** calcula, por nodo, la variación temporal de las amplitudes
   (coeficiente de variación en ventana de 2 s). Habitación quieta → señal
   estable. Persona moviéndose → varianza alta.
3. Con una **calibración** de la casa vacía se calcula el z-score y se
   clasifica cada habitación: `vacío` / `presencia` / `movimiento`.
4. El **dashboard** muestra las plantas y habitaciones en tiempo real.

## Qué puede y qué NO puede hacer (honestidad ante todo)

| Capacidad | ¿Realista? |
|---|---|
| Detectar movimiento por habitación | ✅ Sí, funciona bien |
| Detectar en qué planta hay gente | ✅ Sí |
| Varias personas en habitaciones distintas | ✅ Sí (una por habitación) |
| Contar cuántas personas hay en una habitación | ⚠️ No fiable |
| Persona completamente quieta (durmiendo) | ⚠️ Difícil (requiere detectar respiración, avanzado) |
| Identificar QUIÉN es cada persona | ❌ No con este hardware (es tema de investigación) |
| "Ver" siluetas tipo DensePose | ❌ Requiere hardware de investigación (Intel 5300, arrays de antenas) |

## Hardware necesario

- 1 × ESP32 dev board por habitación a vigilar (~5 €/ud, cualquier `esp32dev`)
- 1 × ordenador siempre encendido para el servidor (una Raspberry Pi vale)
- Tu router WiFi de siempre — no hace falta tocarlo

Ver [docs/hardware.md](docs/hardware.md) para consejos de colocación.

## Prueba rápida SIN hardware (simulador)

```bash
cd server
pip install -r requirements.txt
python server.py
```

En otra terminal:

```bash
cd tools
python simulate.py
```

Abre <http://localhost:8080> — verás una "persona" simulada moviéndose por las
habitaciones del `config.yaml`.

## Puesta en marcha real

### 1. Flashear los ESP32

Con [PlatformIO](https://platformio.org/) instalado:

```bash
cd firmware/esp32-csi-node
WIFI_SSID=TuWifi WIFI_PASS=TuClave NODE_ID=1 SERVER_IP=192.168.1.50 pio run -t upload
```

Repite con `NODE_ID=2`, `3`… para cada nodo. `SERVER_IP` es la IP del
ordenador que ejecuta el servidor.

### 2. Configurar el mapa de la casa

Edita `server/config.yaml` y asigna cada `node_id` a su habitación y planta.

### 3. Calibrar (casa vacía o todos quietos)

```bash
cd tools
python calibrate.py --seconds 60
```

Esto graba la línea base de ruido de cada nodo en `server/calibration.json`.
Recalibra si mueves un nodo o cambias muebles grandes.

### 4. Arrancar

```bash
cd server
python server.py
```

Dashboard en `http://<ip-del-servidor>:8080`.

## Estructura

```
wifi-tracking/
├── firmware/esp32-csi-node/   # ESP-IDF: captura CSI + envío UDP
├── server/
│   ├── server.py              # ingesta UDP + API + dashboard
│   ├── csi_packet.py          # parseo del paquete binario
│   ├── features.py            # métrica de movimiento (CV en ventana)
│   ├── detector.py            # clasificación por z-score
│   ├── localizer.py           # fusión nodos → habitaciones/plantas
│   ├── config.yaml            # mapa de tu casa y umbrales
│   └── static/index.html      # dashboard
├── tools/
│   ├── simulate.py            # probar todo sin hardware
│   └── calibrate.py           # grabar línea base
└── docs/hardware.md
```

## Mover este proyecto a su propio repositorio

Este proyecto vive como subcarpeta por limitaciones de acceso de la sesión en
que se creó. Para independizarlo:

```bash
# crea el repo vacío en GitHub (p.ej. wifi-person-tracking) y luego:
cp -r wifi-tracking ~/wifi-person-tracking
cd ~/wifi-person-tracking
git init && git add -A && git commit -m "Initial commit"
git remote add origin git@github.com:alest-arch/wifi-person-tracking.git
git push -u origin main
```

## Ideas para seguir jugando

- Detección de respiración (persona quieta) con FFT sobre la fase del CSI
- Clasificador ML (scikit-learn) en vez de umbral: distinguir andar / gesticular / mascota
- Histórico en SQLite + gráficas de ocupación por horas
- Integración con Home Assistant vía MQTT
