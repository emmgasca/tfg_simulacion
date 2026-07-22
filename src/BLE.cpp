#include <Arduino.h>
#include <NimBLEDevice.h>
#include <cstring>
#include "hal.h"
#include "ads1298.h"

#define SERVICE_EMG     "12345678-1234-1234-1234-123456789abc"
#define SERVICE_IMU     "87654321-1234-1234-1234-123456789abc"
#define CHAR_EMG_DATA  "aaaaaaaa-1234-1234-1234-123456789abc"
#define CHAR_EMG_CONFIG   "bbbbbbbb-1234-1234-1234-123456789abc"
#define CHAR_IMU_DATA   "cccccccc-1234-1234-1234-123456789abc"
#define CHAR_IMU_CONFIG   "dddddddd-1234-1234-1234-123456789abc"
#define CHAR_EVENTOS_DATA "eeeeeeee-1234-1234-1234-123456789abc"

// Cuántas muestras EMG se agrupan en cada notify BLE.
// 10 muestras x 24 bytes = 240 bytes, dentro del MTU negociado (247 -> 244 bytes útiles).
static constexpr uint8_t MUESTRAS_POR_PAQUETE = 10;
static constexpr size_t BYTES_PAQUETE_EMG = MUESTRAS_POR_PAQUETE * ADS1298::BYTES_POR_MUESTRA;

// Tiempo mínimo entre pulsaciones válidas de un mismo botón (antirrebote).
static constexpr uint32_t DEBOUNCE_MS = 200;

enum TipoEvento : uint8_t {
    EVENTO_STOP  = 0,
    EVENTO_START = 1,
    EVENTO_MARK  = 2,
};

QueueHandle_t queueEMG;
QueueHandle_t queueIMU;

// Estado de grabación controlado por el botón START/STOP (KEY1) y contador de
// muestras EMG tomadas desde el último START, usado para poder alinear los
// eventos (START/STOP/MARK) con la fila correspondiente en los datos EMG.
static volatile bool midiendo = false;
static volatile uint32_t contadorMuestras = 0;

void taskEMG(void* param);
void taskIMU(void* param);
void taskBLE(void* param);

void bleSetup(){
    // Cola con margen para absorber ráfagas sin perder muestras si el consumidor BLE se retrasa.
    queueEMG = xQueueCreate(60, ADS1298::BYTES_POR_MUESTRA);
    queueIMU = xQueueCreate(10, sizeof(float) * 3);

    // Configurar pines LED
    pinMode(LED_PIN_RGB_Red, OUTPUT);
    pinMode(LED_PIN_RGB_Blue, OUTPUT);
    //pinMode(LED_PIN_RGB_Green, OUTPUT);
    digitalWrite(LED_PIN_RGB_Red, LOW);
    digitalWrite(LED_PIN_RGB_Blue, HIGH);
    //digitalWrite(LED_PIN_RGB_Green, LOW);

    // Botones KEY1 (START/STOP) y KEY2 (MARK): activos en bajo, con pull-up interno.
    pinMode(START_STOP, INPUT_PULLUP);
    pinMode(MARK, INPUT_PULLUP);

    xTaskCreate(taskEMG, "taskEMG", 2048, NULL, 1, NULL);
    xTaskCreate(taskIMU, "taskIMU", 2048, NULL, 1, NULL);
    xTaskCreate(taskBLE, "taskBLE", 8192, NULL, 1, NULL);
}
void taskEMG (void* param){
    uint32_t muestrasEsteSegundo = 0;
    uint32_t ultimoReporte = millis();
    uint32_t ultimoYield = millis();
    while(true){
        uint8_t muestra[ADS1298::BYTES_POR_MUESTRA];
        if (ads.readChannels(muestra)) {
            // Solo se encola/cuenta mientras se está grabando (START pulsado).
            if (midiendo) {
                // Envío bloqueante (con margen): si la cola está llena se espera en vez de
                // descartar la muestra silenciosamente. Solo se pierde si el consumidor BLE
                // lleva más de 50 ms sin drenar (p. ej. desconectado).
                xQueueSend(queueEMG, muestra, pdMS_TO_TICKS(50));
                contadorMuestras++;
                muestrasEsteSegundo++;
            }
            // vTaskDelay(0) (yield) NO basta: en FreeRTOS solo cede a tareas de
            // igual prioridad, y como esta tarea vuelve a estar lista al instante,
            // el planificador nunca le da hueco real a IDLE0 (prioridad más baja),
            // que nunca llega a resetear el watchdog -> abort() (visto en hardware:
            // "Task watchdog got triggered ... taskEMG"). Hace falta un bloqueo
            // real y periódico. Para no desacoplar la captura del reloj del ADC
            // (eso submuestrea/alía la señal) solo se fuerza cada ~5 ms de reloj,
            // no en cada muestra.
            if (millis() - ultimoYield >= 5) {
                vTaskDelay(pdMS_TO_TICKS(1));
                ultimoYield = millis();
            }
        } else {
            vTaskDelay(pdMS_TO_TICKS(1));
        }

        if (millis() - ultimoReporte >= 1000) {
            if (mutexSerial != NULL) {
                xSemaphoreTake(mutexSerial, portMAX_DELAY);
            }
            Serial.printf("Tasa real EMG: %lu muestras/s\n", (unsigned long)muestrasEsteSegundo);
            if (mutexSerial != NULL) {
                xSemaphoreGive(mutexSerial);
            }
            muestrasEsteSegundo = 0;
            ultimoReporte = millis();
        }
    }
}
void taskIMU (void* param){
    while (true){
        float muestraIMU[3];
        muestraIMU[0] = sin(millis() / 1000.0f);
        muestraIMU[1] = sin(millis() / 1000.0f + 1.0f);
        muestraIMU[2] = sin(millis() / 1000.0f + 2.0f);
        xQueueSend(queueIMU, muestraIMU, 0);
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}
// Notifica un evento (START/STOP/MARK) con el índice de muestra EMG en el
// que ocurrió, para poder alinearlo luego con las filas capturadas en Python.
static void enviarEvento(NimBLECharacteristic* pCharEventosData, TipoEvento tipo) {
    uint8_t payload[5];
    payload[0] = (uint8_t)tipo;
    uint32_t muestra_actual = contadorMuestras;
    memcpy(&payload[1], &muestra_actual, sizeof(muestra_actual));
    pCharEventosData->setValue(payload, sizeof(payload));
    pCharEventosData->notify();
}

void taskBLE (void* param){
    // MTU ampliado para poder enviar el buffer agrupado de muestras en un solo notify.
    //NimBLEDevice::setMTU(247);
    //Iniciar NimBLE
    NimBLEDevice::init("ESP32");
    //Crear Servidor BLE
    NimBLEServer* pServer = NimBLEDevice::createServer();
    //Crear Servicio EMG
    NimBLEService* pServiceEMG = pServer->createService(SERVICE_EMG);
    //Crear Char EMG DATA
    NimBLECharacteristic* pCharEMGData = pServiceEMG->createCharacteristic(CHAR_EMG_DATA, NIMBLE_PROPERTY::NOTIFY);
    //Crear Char EMG CONFIG
    NimBLECharacteristic* pCharEMGConfig = pServiceEMG->createCharacteristic(CHAR_EMG_CONFIG, NIMBLE_PROPERTY::WRITE);
    //Crear Char EVENTOS (START/STOP/MARK)
    NimBLECharacteristic* pCharEventosData = pServiceEMG->createCharacteristic(CHAR_EVENTOS_DATA, NIMBLE_PROPERTY::NOTIFY);
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

    // Estado previo de los botones para detectar flancos de pulsación (HIGH -> LOW).
    bool estadoAnteriorStartStop = HIGH;
    bool estadoAnteriorMark = HIGH;
    uint32_t ultimoCambioStartStop = 0;
    uint32_t ultimoCambioMark = 0;

    while(true){

        // ====== LED AZUL: Conectado BLE ======
        if (pServer->getConnectedCount() > 0) {
            digitalWrite(LED_PIN_RGB_Blue, HIGH);  // Conectado
        } else {
            digitalWrite(LED_PIN_RGB_Blue, LOW);   // Desconectado
        }

        // ====== Botón START/STOP (KEY1): alterna la grabación ======
        bool estadoStartStop = digitalRead(START_STOP);
        if (estadoAnteriorStartStop == HIGH && estadoStartStop == LOW &&
            (millis() - ultimoCambioStartStop) > DEBOUNCE_MS) {
            if (!midiendo) {
                contadorMuestras = 0;
                midiendo = true;
                enviarEvento(pCharEventosData, EVENTO_START);
                if (mutexSerial != NULL) xSemaphoreTake(mutexSerial, portMAX_DELAY);
                Serial.println("KEY1 pulsado -> START (midiendo=true)");
                if (mutexSerial != NULL) xSemaphoreGive(mutexSerial);
            } else {
                midiendo = false;
                enviarEvento(pCharEventosData, EVENTO_STOP);
                if (mutexSerial != NULL) xSemaphoreTake(mutexSerial, portMAX_DELAY);
                Serial.printf("KEY1 pulsado -> STOP (midiendo=false, %lu muestras)\n", (unsigned long)contadorMuestras);
                if (mutexSerial != NULL) xSemaphoreGive(mutexSerial);
            }
            ultimoCambioStartStop = millis();
        }
        estadoAnteriorStartStop = estadoStartStop;

        // ====== Botón MARK (KEY2): marca un evento puntual ======
        bool estadoMark = digitalRead(MARK);
        if (estadoAnteriorMark == HIGH && estadoMark == LOW &&
            (millis() - ultimoCambioMark) > DEBOUNCE_MS) {
            enviarEvento(pCharEventosData, EVENTO_MARK);
            if (mutexSerial != NULL) xSemaphoreTake(mutexSerial, portMAX_DELAY);
            Serial.printf("KEY2 pulsado -> MARK (muestra #%lu)\n", (unsigned long)contadorMuestras);
            if (mutexSerial != NULL) xSemaphoreGive(mutexSerial);
            ultimoCambioMark = millis();
        }
        estadoAnteriorMark = estadoMark;

        uint8_t muestra[ADS1298::BYTES_POR_MUESTRA];
        bool enviadoEMG = false;

        // Se drena toda la cola disponible (no solo una muestra) para no acumular
        // retraso si llegaron varias muestras desde la última vuelta del bucle.
        while (xQueueReceive(queueEMG, muestra, 0) == pdTRUE) {
            memcpy(&bufferEMG[indiceEMG * ADS1298::BYTES_POR_MUESTRA], muestra, ADS1298::BYTES_POR_MUESTRA);
            indiceEMG++;
            if (indiceEMG >= MUESTRAS_POR_PAQUETE) {
                pCharEMGData->setValue(bufferEMG, BYTES_PAQUETE_EMG);
                pCharEMGData->notify();
                indiceEMG = 0;
                enviadoEMG = true;
            }
        }
        float imu[3];
        bool enviadoIMU = false;

        if(xQueueReceive(queueIMU, imu,0)){
            pCharIMUData->setValue((uint8_t*)imu, sizeof(float) * 3);
            pCharIMUData->notify();
            enviadoIMU = true;
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