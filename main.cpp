#include <Arduino.h>
#include <SPI.h>
#include "ads1298.h"
#include "hal.h"

#define PIN_CS 10

void setup() {
    Serial.begin(115200);
    delay(3000);
    Serial.println("Hola");

    // Encender y resetear el ADS1298
    pinMode(7, OUTPUT);   // PWDN_n //1
    pinMode(6, OUTPUT);   // ADS_Reset_n //2
    pinMode(5, INPUT);    // DRDY_n //5
    pinMode(8, OUTPUT);  // Start_Data //15
    digitalWrite(7, HIGH);
    digitalWrite(8, LOW);
    delay(100);
    digitalWrite(6, LOW);
    delay(10);
    digitalWrite(6, HIGH);
    delay(5);
    Serial.println("Reset OK");

    // Iniciar SPI
    pinMode(PIN_CS, OUTPUT);
    digitalWrite(PIN_CS, HIGH);
    SPI.begin(12, 13, 11, 10); //12,13,11,10
    Serial.println("SPI OK");

    // Comando SDATAC
    SPI.beginTransaction(SPISettings(500000, MSBFIRST, SPI_MODE1));
    digitalWrite(PIN_CS, LOW);
    SPI.transfer(0x11);
    digitalWrite(PIN_CS, HIGH);
    SPI.endTransaction();
    delay(10);
    Serial.println("SDATAC OK");
    

    // RESET por comando SPI
    SPI.beginTransaction(SPISettings(500000, MSBFIRST, SPI_MODE1));
    digitalWrite(PIN_CS, LOW);
    SPI.transfer(0x06);  // RESET
    digitalWrite(PIN_CS, HIGH);
    SPI.endTransaction();
    delay(100);

    SPI.beginTransaction(SPISettings(500000, MSBFIRST, SPI_MODE1));
    digitalWrite(PIN_CS, LOW);
    SPI.transfer(0x11);
    digitalWrite(PIN_CS, HIGH);
    SPI.endTransaction();
    delay(10);

    // Leer registro ID
    SPI.beginTransaction(SPISettings(500000, MSBFIRST, SPI_MODE1));
    digitalWrite(PIN_CS, LOW);
    SPI.transfer(0x20);
    SPI.transfer(0x00);
    uint8_t id = SPI.transfer(0x00);
    digitalWrite(PIN_CS, HIGH);
    SPI.endTransaction();

    Serial.print("ID: 0x");
    Serial.println(id, HEX);

    //Escribir registro CONFIG1
    SPI.beginTransaction(SPISettings(500000, MSBFIRST, SPI_MODE1));
    digitalWrite(PIN_CS, LOW);
    SPI.transfer(0x41);  // WREG | CONFIG1
    SPI.transfer(0x00);  // 1 registro
    SPI.transfer(0x86);  // valor que quieres escribir
    digitalWrite(PIN_CS, HIGH);
    SPI.endTransaction();

    // Leer CONFIG1 para verificar
    SPI.beginTransaction(SPISettings(500000, MSBFIRST, SPI_MODE1));
    digitalWrite(PIN_CS, LOW);
    SPI.transfer(0x21);  // RREG | 0x01
    SPI.transfer(0x00);
    uint8_t config1 = SPI.transfer(0x00);
    digitalWrite(PIN_CS, HIGH);
    SPI.endTransaction();

    Serial.print("CONFIG1 leido: 0x");
    Serial.println(config1, HEX);


     //Mandar comando STOP
    SPI.beginTransaction(SPISettings(500000, MSBFIRST, SPI_MODE1));
    digitalWrite(PIN_CS, LOW);
    SPI.transfer(0x0A);  // STOP
    digitalWrite(PIN_CS, HIGH);
    SPI.endTransaction();

    Serial.println("STOP OK");

    //Mandar comando START
    SPI.beginTransaction(SPISettings(500000, MSBFIRST, SPI_MODE1));
    digitalWrite(PIN_CS, LOW);
    SPI.transfer(0x08);  // START
    digitalWrite(PIN_CS, HIGH);
    SPI.endTransaction();

     Serial.println("START OK");

    
}

void loop() {
    while (digitalRead(5) == HIGH) { //chip avisa de datos listos, baja a low cada vez que hay una muestra
        delay(10);
    }
    Serial.println("DRDY bajo - datos listos");

    //Mandar comando RDATA
    SPI.beginTransaction(SPISettings(500000, MSBFIRST, SPI_MODE1));
    digitalWrite(PIN_CS, LOW);
    SPI.transfer(0x12);  // RDATA

    Serial.println("RDATA OK");

    int numBytes = 27; // 3 bytes de estado + 8 canales * 3 bytes cada uno
    uint8_t frame[numBytes];
    for (int i = 0; i < numBytes; i++) {
        frame[i] = SPI.transfer(0x00);
    }
    digitalWrite(PIN_CS, HIGH);
    SPI.endTransaction();

    Serial.println("Datos leidos:");
    for (int i = 0; i < numBytes; i++) {
        Serial.print(", 0x");
        Serial.print(frame[i], HEX);
        Serial.print("");
    }
    Serial.println();

    //recorrer los canales
    for (int ch = 0; ch < 8; ch++) {
        int32_t value = (frame[3 + ch * 3] << 16) | (frame[4 + ch * 3] << 8) | frame[5 + ch * 3];
        //cada canal 3 bytes por separado, lo juntamos desplazando y haciendo OR
        if (value & 0x800000) { // num más pequeño
            value |= 0xFF000000; // Extender el signo
        }
        
        Serial.print("Canal ");
        Serial.print(ch + 1);
        Serial.print(": ");
        Serial.println(value);
    }

}
