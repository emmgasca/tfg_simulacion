#include <Arduino.h>
#include <NimBLEDevice.h>
#include <cstring>
#include "hal.h"
#include "ads1298.h"
#include "botones.h"
#include "imu.h"

#define SERVICE_EMG     "12345678-1234-1234-1234-123456789abc"
#define SERVICE_IMU     "87654321-1234-1234-1234-123456789abc"
#define CHAR_EMG_DATA  "aaaaaaaa-1234-1234-1234-123456789abc"
#define CHAR_EMG_CONFIG   "bbbbbbbb-1234-1234-1234-123456789abc"
#define CHAR_IMU_DATA   "cccccccc-1234-1234-1234-123456789abc"
#define CHAR_IMU_CONFIG   "dddddddd-1234-1234-1234-123456789abc"
#define CHAR_EVENT_DATA "eeeeeeee-1234-1234-1234-123456789abc"

// EXPERIMENTO: formato de paquete de antes de adaptarlo a ParkEMG (sin
// magic/version/CRC16, solo un contador de PAQUETE de 2 bytes) -- para
// aislar si la perdida original era solo cuestion de tamano de paquete o si
// de verdad hacia falta el framing/CRC de ParkEMG. Unico cambio respecto al
// formato de entonces: MUESTRAS_POR_PAQUETE baja de 10 a 8, el mismo margen
// (~45-49 bytes bajo el techo de ~248-252 bytes de NimBLE-Arduino, ver
// CONFIG_BT_NIMBLE_ACL_BUF_SIZE) que ya se valido con el formato PB v2 y dejo
// la perdida en 0. El tuning de conexion (CallbacksServidor, mas abajo) se
// mantiene igual: eso ya se demostro necesario aparte del tamano de paquete.
static constexpr uint8_t MUESTRAS_POR_PAQUETE = 8;
static constexpr size_t BYTES_PAQUETE_EMG = MUESTRAS_POR_PAQUETE * ADS1298::BYTES_POR_MUESTRA;
static constexpr size_t BYTES_CABECERA_EMG = 2;  // num. de paquete, 16 bits, little-endian
static constexpr size_t BYTES_NOTIFY_EMG = BYTES_CABECERA_EMG + BYTES_PAQUETE_EMG;

QueueHandle_t queueEMG;
QueueHandle_t queueIMU;

void taskEMG(void* param);
void taskIMU(void* param);
void taskBLE(void* param);

// Callbacks de conexion BLE: sin esto, el firmware nunca ve el MTU realmente
// negociado (solo se ve lo que se PIDE con setMTU(), no lo que el central
// acepta) ni pide parametros de conexion/Data Length Extension mejores que
// los que trae NimBLE por defecto -- ambos relevantes para sostener el
// throughput que exige el EMG a 2 kHz (~400+ kbps).
class CallbacksServidor : public NimBLEServerCallbacks {
    void onConnect(NimBLEServer* pServer, ble_gap_conn_desc* desc) override {
        // conn_itvl viene en unidades de 1.25 ms; supervision_timeout en
        // unidades de 10 ms. OJO: esto es el intervalo INICIAL que propuso
        // el central antes de pedir updateConnParams() mas abajo, no el
        // valor final tras la renegociacion (NimBLEServerCallbacks no tiene
        // un callback para "parametros actualizados" en esta version). Aun
        // asi sirve de referencia: si ya de entrada es un intervalo largo
        // (30-50 ms), el central puede no estar aceptando negociaciones mas
        // agresivas despues.
        Serial.printf("BLE: cliente conectado (handle=%d) | intervalo inicial=%.2fms latencia=%u timeout=%ums\n",
                      desc->conn_handle,
                      desc->conn_itvl * 1.25,
                      (unsigned)desc->conn_latency,
                      (unsigned)desc->supervision_timeout * 10);
        // Intervalo corto (7.5-15 ms) y sin latencia, para maximizar cuantos
        // notify/s caben en el enlace. El central tiene la ultima palabra y
        // puede no conceder justo esto, pero es lo maximo que el periferico
        // puede pedir.
        pServer->updateConnParams(desc->conn_handle, 6, 12, 0, 400);
        // Data Length Extension al maximo permitido por el estandar (251
        // bytes de payload de enlace), para que un notify no se fragmente en
        // paquetes de 27 bytes (el valor por defecto sin DLE).
        pServer->setDataLen(desc->conn_handle, 251);
    }

    void onDisconnect(NimBLEServer* pServer, ble_gap_conn_desc* desc) override {
        Serial.println("BLE: cliente desconectado, reanudando advertising...");
        NimBLEDevice::startAdvertising();
    }

    void onMTUChange(uint16_t mtu, ble_gap_conn_desc* desc) override {
        // Esto es lo que hasta ahora no se podia ver: el MTU que de verdad
        // negocia el cliente (Windows/bleak), no el que la libreria PREFIERE.
        // Con MUESTRAS_POR_PAQUETE=8, BYTES_NOTIFY_EMG (ver mas abajo) debe
        // caber en mtu - 3 para que ningun paquete EMG se trunque en silencio.
        Serial.printf("BLE: MTU negociado = %u bytes (util para notify: %d bytes)\n",
                      (unsigned)mtu, (int)mtu - 3);
    }
};
static CallbacksServidor callbacksServidor;

void bleSetup(){
    // Cola con margen para absorber ráfagas sin perder muestras si el consumidor BLE se retrasa.
    queueEMG = xQueueCreate(60, ADS1298::BYTES_POR_MUESTRA);
    queueIMU = xQueueCreate(10, sizeof(float) * 3);

    xTaskCreate(taskEMG, "taskEMG", 8192, NULL, 1, NULL);
    // xTaskCreate(taskIMU, "taskIMU", 2048, NULL, 1, NULL);
    xTaskCreate(taskBLE, "taskBLE", 8192, NULL, 1, NULL);
}
void taskEMG (void* param){
    uint32_t muestrasEsteSegundo = 0;
    uint32_t colaLlenaEsteSegundo = 0;
    uint32_t ultimoReporte = millis();
    while(true){
        uint8_t muestra[ADS1298::BYTES_POR_MUESTRA];
        if (ads.readChannels(muestra)) {
            // contadorMuestras se incrementa aquí, justo tras leer el ADC y
            // antes de la cola BLE, para que cuente de verdad "muestras
            // procesadas por el firmware" (como dice guardar.py) y no solo
            // las que sobrevivieron a la cola/BLE. Si se incrementara
            // después de xQueueSend, un desbordamiento de queueEMG (cola
            // llena porque BLE no drena tan rápido como el ADC produce)
            // quedaría invisible para la comparación de pérdidas en STOP.
            if (grabando) {
                contadorMuestras++;
            }
            if (xQueueSend(queueEMG, muestra, pdMS_TO_TICKS(50)) != pdTRUE) {
                colaLlenaEsteSegundo++;
            }
            muestrasEsteSegundo++;
            // Sin delay aquí: readChannels() ya bloquea de verdad en
            // waitForDRDY() (semáforo dado por la ISR de DRDY), así que la
            // tarea cede la CPU entre muestras sin necesidad de un delay
            // artificial que descartaría conversiones del ADC.
        }
        // else {
        //     vTaskDelay(pdMS_TO_TICKS(1));
        // }

        if (millis() - ultimoReporte >= 1000) {
            Serial.printf(
                "Tasa real EMG: %lu muestras/s | exitos=%lu timeoutDRDY=%lu sincFail=%lu ceros=%lu perdidasDRDY=%lu | colaLlena=%lu\n",
                (unsigned long)muestrasEsteSegundo,
                (unsigned long)ads.estadisticas.exitos,
                (unsigned long)ads.estadisticas.timeoutsDRDY,
                (unsigned long)ads.estadisticas.fallosSincronismo,
                (unsigned long)ads.estadisticas.descartesCeros,
                (unsigned long)ads.estadisticas.perdidasDRDY,
                (unsigned long)colaLlenaEsteSegundo);
            ads.estadisticas.exitos = 0;
            ads.estadisticas.timeoutsDRDY = 0;
            ads.estadisticas.fallosSincronismo = 0;
            ads.estadisticas.descartesCeros = 0;
            ads.estadisticas.perdidasDRDY = 0;
            muestrasEsteSegundo = 0;
            colaLlenaEsteSegundo = 0;
            ultimoReporte = millis();
        }
    }
}
void taskIMU (void* param){
    while (true){
        float muestraIMU[3];
        if (imuLeerAcelerometro(muestraIMU[0], muestraIMU[1], muestraIMU[2])) {
            xQueueSend(queueIMU, muestraIMU, 0);
        }
        // 20 Hz (50ms): de sobra para seguimiento de movimiento, y evita saturar
        // el enlace BLE compitiendo con el EMG (antes eran 200 notify/s de IMU).
        vTaskDelay(pdMS_TO_TICKS(50));
    }
}
void taskBLE (void* param){
    // NimBLEDevice::setMTU(512); -- probado y descartado: rompe la conexion BLE.
    //Iniciar NimBLE
    NimBLEDevice::init("ESP32");
    //Crear Servidor BLE
    NimBLEServer* pServer = NimBLEDevice::createServer();
    pServer->setCallbacks(&callbacksServidor);
    //Crear Servicio EMG
    NimBLEService* pServiceEMG = pServer->createService(SERVICE_EMG);
    //Crear Char EMG DATA
    NimBLECharacteristic* pCharEMGData = pServiceEMG->createCharacteristic(CHAR_EMG_DATA, NIMBLE_PROPERTY::NOTIFY);
    //Crear Char EMG CONFIG
    NimBLECharacteristic* pCharEMGConfig = pServiceEMG->createCharacteristic(CHAR_EMG_CONFIG, NIMBLE_PROPERTY::WRITE);
    //Crear Char EVENT DATA (START/STOP/MARK)
    // INDICATE en vez de NOTIFY: a diferencia de NOTIFY (envío sin confirmación,
    // que se puede perder en silencio si el enlace está saturado por el tráfico
    // EMG), INDICATE espera el ACK del receptor antes de considerarse enviado,
    // así que no se pierden eventos aunque haya mucho tráfico EMG compitiendo
    // por el mismo enlace. Confirmado en pruebas: con NOTIFY se perdían ~80% de
    // los eventos MARK durante una grabación EMG activa.
    NimBLECharacteristic* pCharEventData = pServiceEMG->createCharacteristic(CHAR_EVENT_DATA, NIMBLE_PROPERTY::INDICATE);
    //Crear Servicio IMU
    NimBLEService* pServiceIMU = pServer->createService(SERVICE_IMU);
    //Crear Char IMU DATA
    NimBLECharacteristic* pCharIMUData = pServiceIMU->createCharacteristic(CHAR_IMU_DATA, NIMBLE_PROPERTY::NOTIFY);
    //Crear Char IMU CONFIG         
    NimBLECharacteristic* pCharIMUConfig = pServiceIMU->createCharacteristic(CHAR_IMU_CONFIG, NIMBLE_PROPERTY::WRITE);  

    pServiceEMG->start();
    pServiceIMU->start();
    NimBLEDevice::getAdvertising()->start();

    // Buffer donde se agrupan MUESTRAS_POR_PAQUETE muestras EMG antes de notificar.
    uint8_t bufferEMG[BYTES_PAQUETE_EMG];
    uint8_t indiceEMG = 0;

    // Paquete final que se envia por BLE: contador de paquete (2 bytes, no de
    // muestra) + muestras, sin CRC. El PC reconstruye una secuencia por
    // muestra multiplicando este contador por MUESTRAS_POR_PAQUETE.
    uint8_t paqueteEMG[BYTES_NOTIFY_EMG];
    uint16_t contadorPaquetesEMG = 0;

    while(true){

        // LED AZUL: Conectado BLE 
        if (pServer->getConnectedCount() > 0) {
            digitalWrite(LED_PIN_RGB_Blue, HIGH);  // Conectado
        } else {
            digitalWrite(LED_PIN_RGB_Blue, LOW);   // Desconectado
        }

        uint8_t muestra[ADS1298::BYTES_POR_MUESTRA];
        bool enviadoEMG = false;

        // Se drena toda la cola disponible (no solo una muestra) para no acumular
        // retraso si llegaron varias muestras desde la última vuelta del bucle.
        // Solo se empaqueta y envía si hay una sesión de grabación activa (botón START/STOP).
        while (xQueueReceive(queueEMG, muestra, 0) == pdTRUE) {
            if (grabando) {
                memcpy(&bufferEMG[indiceEMG * ADS1298::BYTES_POR_MUESTRA], muestra, ADS1298::BYTES_POR_MUESTRA);
                indiceEMG++;
                if (indiceEMG >= MUESTRAS_POR_PAQUETE) {
                    paqueteEMG[0] = (uint8_t)(contadorPaquetesEMG & 0xFF);
                    paqueteEMG[1] = (uint8_t)((contadorPaquetesEMG >> 8) & 0xFF);
                    memcpy(&paqueteEMG[BYTES_CABECERA_EMG], bufferEMG, BYTES_PAQUETE_EMG);

                    pCharEMGData->setValue(paqueteEMG, BYTES_NOTIFY_EMG);
                    pCharEMGData->notify();
                    contadorPaquetesEMG++;
                    indiceEMG = 0;
                    enviadoEMG = true;
                }
            }
        }

        float imu[3];
        bool enviadoIMU = false;

        if(xQueueReceive(queueIMU, imu,0)){
            pCharIMUData->setValue((uint8_t*)imu, sizeof(float) * 3);
            pCharIMUData->notify();
            enviadoIMU = true;
        }

        // Eventos de botones (START/STOP/MARK)
        EventoBLE evento;
        while (xQueueReceive(queueEventos, &evento, 0) == pdTRUE) {
            uint8_t buf[9];
            buf[0] = evento.tipo;
            memcpy(&buf[1], &evento.muestra, 4);
            memcpy(&buf[5], &evento.timestamp_ms, 4);
            pCharEventData->setValue(buf, 9);
            // false = pedir explícitamente una indicación (con ACK), no una notificación.
            // notify() por defecto usa is_notification=true; aunque NimBLE se autocorrige
            // si detecta un cliente suscrito solo a indicaciones, esa autocorrección
            // depende de un estado de suscripción que se resuelve de forma asíncrona, y
            // si el evento llega antes de que se resuelva, se descarta en silencio.
            pCharEventData->notify(false);
        }

        // Red = cuando hay datos siendo enviados
        if (enviadoEMG || enviadoIMU) {
            digitalWrite(LED_PIN_RGB_Red, HIGH);
        } else {
            digitalWrite(LED_PIN_RGB_Red, LOW);
        }

        vTaskDelay(pdMS_TO_TICKS(5));
    }
}
void bleLoop(){}