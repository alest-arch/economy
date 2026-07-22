# Hardware y colocación de los nodos

## Lista de la compra

| Qué | Cantidad | Precio aprox. |
|---|---|---|
| ESP32 DevKit (ESP32-WROOM-32) | 1 por habitación | 4–7 € |
| Cable micro-USB + cargador 5V | 1 por nodo | reutiliza los que tengas |
| Ordenador para el servidor | 1 | Raspberry Pi, un portátil viejo… |

No compres ESP32-C3/S2 de un solo núcleo si puedes evitarlo: el WROOM-32
clásico va sobrado y es el que más documentación CSI tiene.

## Dónde colocar cada nodo

La detección se basa en que la persona cruce o altere los caminos de la señal
entre el **nodo** y el **router**. Consejos:

- Coloca el nodo en el lado de la habitación **opuesto** al router: así el
  "camino" de la señal atraviesa la zona por la que se mueve la gente.
- Altura media (una estantería, 1–1,5 m). Ni en el suelo ni pegado al techo.
- Evita pegarlo a objetos metálicos grandes (nevera, radiador).
- Una habitación grande o con forma de L puede necesitar 2 nodos — añade los
  dos al `config.yaml` con la misma `room`.

## Varias plantas

La señal entre plantas se atenúa mucho (forjado de hormigón ≈ 10–20 dB), lo
cual aquí es una **ventaja**: cada nodo "ve" sobre todo su propia planta, así
que hay poca contaminación cruzada. Basta con:

- 1–2 nodos por planta como mínimo (uno por habitación relevante ideal)
- Todos los nodos conectados al mismo SSID; si tienes red mesh, mejor aún

## Sobre el router

No hace falta tocar nada del router. Los ESP32 solo necesitan:

- WiFi **2,4 GHz** habilitada (el CSI del ESP32 es solo 2,4 GHz)
- Que el router responda a ping (todos lo hacen por defecto)

Si tu red separa 2,4/5 GHz en SSIDs distintos, conecta los nodos al de 2,4.

## Consumo

Cada ESP32 con `WIFI_PS_NONE` consume ~0,5–0,8 W. Cuatro nodos encendidos
24/7 ≈ 2,5 kWh/mes (menos de 1 € al mes).
