#include <Arduino.h>
#include <NimBLEDevice.h>
#include "hal.h"


#define SERVICE_EMG     "12345678-1234-1234-1234-123456789abc"
#define SERVICE_IMU     "87654321-1234-1234-1234-123456789abc"
#define CHAR_EMG_DATA  "aaaaaaaa-1234-1234-1234-123456789abc"
#define CHAR_EMG_CONFIG   "bbbbbbbb-1234-1234-1234-123456789abc"
#define CHAR_IMU_DATA   "cccccccc-1234-1234-1234-123456789abc"
#define CHAR_IMU_CONFIG   "dddddddd-1234-1234-1234-123456789abc"

QueueHandle_t queueEMG;
QueueHandle_t queueIMU;

void taskEMG(void* param);
void taskIMU(void* param);
void taskBLE(void* param);

void bleSetup(){
    queueEMG = xQueueCreate(10, sizeof(float));
    queueIMU = xQueueCreate(10, sizeof(float) * 3);

    // Configurar pines LED
    pinMode(LED_PIN_RGB_Red, OUTPUT);
    pinMode(LED_PIN_RGB_Blue, OUTPUT);
    pinMode(LED_PIN_RGB_Green, OUTPUT);
    digitalWrite(LED_PIN_RGB_Red, LOW);
    digitalWrite(LED_PIN_RGB_Blue, LOW);
    digitalWrite(LED_PIN_RGB_Green, LOW);

    xTaskCreate(taskEMG, "taskEMG", 2048, NULL, 1, NULL);
    xTaskCreate(taskIMU, "taskIMU", 2048, NULL, 1, NULL);
    xTaskCreate(taskBLE, "taskBLE", 4096, NULL, 1, NULL);
}
void taskEMG (void* param){
    while(true){
        float muestraEMG = sin(millis() / 1000.0f);
        xQueueSend(queueEMG, &muestraEMG, 0);
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

    while(true){

        // ====== LED AZUL: Conectado BLE ======
        if (pServer->getConnectedCount() > 0) {
            digitalWrite(LED_PIN_RGB_Blue, HIGH);  // Conectado
        } else {
            digitalWrite(LED_PIN_RGB_Blue, LOW);   // Desconectado
        }



        float emg;
        bool enviadoEMG = false;

        if(xQueueReceive(queueEMG, &emg,0)){
            pCharEMGData->setValue((uint8_t*)&emg, sizeof(float));
            pCharEMGData->notify();
            enviadoEMG = true;
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

        vTaskDelay(pdMS_TO_TICKS(10));

        
    }
}
void bleLoop(){}