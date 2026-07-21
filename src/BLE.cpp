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

// Cuántas muestras EMG se agrupan en cada notify BLE.
// 10 muestras x 24 bytes = 240 bytes, dentro del MTU negociado (247 -> 244 bytes útiles).
static constexpr uint8_t MUESTRAS_POR_PAQUETE = 10;
static constexpr size_t BYTES_PAQUETE_EMG = MUESTRAS_POR_PAQUETE * ADS1298::BYTES_POR_MUESTRA;

QueueHandle_t queueEMG;
QueueHandle_t queueIMU;

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

    xTaskCreate(taskEMG, "taskEMG", 2048, NULL, 1, NULL);
    xTaskCreate(taskIMU, "taskIMU", 2048, NULL, 1, NULL);
    xTaskCreate(taskBLE, "taskBLE", 4096, NULL, 1, NULL);
}
void taskEMG (void* param){
    while(true){
        uint8_t muestra[ADS1298::BYTES_POR_MUESTRA];
        if (ads.readChannels(muestra)) {
            // Envío bloqueante (con margen): si la cola está llena se espera en vez de
            // descartar la muestra silenciosamente. Solo se pierde si el consumidor BLE
            // lleva más de 50 ms sin drenar (p. ej. desconectado).
            xQueueSend(queueEMG, muestra, pdMS_TO_TICKS(50));
        }
        vTaskDelay(pdMS_TO_TICKS(5));
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
void taskBLE (void* param){
    // MTU ampliado para poder enviar el buffer agrupado de muestras en un solo notify.
    NimBLEDevice::setMTU(247);
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

    while(true){

        // ====== LED AZUL: Conectado BLE ======
        if (pServer->getConnectedCount() > 0) {
            digitalWrite(LED_PIN_RGB_Blue, HIGH);  // Conectado
        } else {
            digitalWrite(LED_PIN_RGB_Blue, LOW);   // Desconectado
        }



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