#include <Arduino.h>

// 定義 LED 腳位
constexpr int LED_LEFT_1_PIN = 25;
constexpr int LED_LEFT_2_PIN = 26;
constexpr int LED_RIGHT_1_PIN = 27;
constexpr int LED_RIGHT_2_PIN = 33;

void setup() {
  // 將這 4 個腳位設定為輸出模式
  pinMode(LED_LEFT_1_PIN, OUTPUT);
  pinMode(LED_LEFT_2_PIN, OUTPUT);
  pinMode(LED_RIGHT_1_PIN, OUTPUT);
  pinMode(LED_RIGHT_2_PIN, OUTPUT);

  // 輸出高電位，讓燈光恆亮 (以 100% 亮度開啟)
  digitalWrite(LED_LEFT_1_PIN, HIGH);
  digitalWrite(LED_LEFT_2_PIN, HIGH);
  digitalWrite(LED_RIGHT_1_PIN, HIGH);
  digitalWrite(LED_RIGHT_2_PIN, HIGH);
}

void loop() {
  // 什麼都不用做，燈光會一直維持在 setup 中設定的恆亮狀態
}