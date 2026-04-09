#include <ESP32Servo.h>

// 定義腳位
const int LEFT_PIN = 18;
const int RIGHT_PIN = 19;

Servo leftServo;
Servo rightServo;

void setup() {
  Serial.begin(115200);
  
  // 分配計時器 (ESP32Servo 必要步驟)
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);

  // 設定頻率與範圍 (500, 2400 是 SG90 的標準脈衝寬度)
  leftServo.setPeriodHertz(50);
  rightServo.setPeriodHertz(50);

  // 連接馬達
  leftServo.attach(LEFT_PIN, 500, 2400);
  rightServo.attach(RIGHT_PIN, 500, 2400);

  // 強制轉到 90 度
  leftServo.write(90);
  rightServo.write(90);

  Serial.println("Servos should be at 90 degrees now.");
}

void loop() {
  // 保持在 90 度，什麼都不做
  delay(1000);
}