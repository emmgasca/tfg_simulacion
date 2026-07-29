#pragma once
#include <Arduino.h>

// Inicializa el bus I2C y el ISM330DLC. Devuelve false si no responde con el
// WHO_AM_I esperado (revisar direccion I2C o cableado si falla).
bool imuBegin();

// Lee una muestra del acelerometro (en g) por I2C. Devuelve false si la
// lectura falla (p.ej. el sensor no respondio).
bool imuLeerAcelerometro(float &x, float &y, float &z);
