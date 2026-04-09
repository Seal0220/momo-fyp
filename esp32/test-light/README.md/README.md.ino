#include <Arduino.h>
#include <FastLED.h>

// 請填入你「每一條」燈條實際的 LED 數量
#define NUM_LEDS 15 

// 建立 4 條燈條的資料陣列
CRGB ledsLeft1[NUM_LEDS];
CRGB ledsLeft2[NUM_LEDS];
CRGB ledsRight1[NUM_LEDS];
CRGB ledsRight2[NUM_LEDS];

// 你的燈條腳位
constexpr int LED_LEFT_1_PIN = 25;
constexpr int LED_LEFT_2_PIN = 26;
constexpr int LED_RIGHT_1_PIN = 27;
constexpr int LED_RIGHT_2_PIN = 33;

void setup() {
  // 初始化 FastLED，告訴它燈條類型 (通常是 WS2812B)、腳位和顏色排列順序 (通常是 GRB)
  FastLED.addLeds<WS2812B, LED_LEFT_1_PIN, GRB>(ledsLeft1, NUM_LEDS);
  FastLED.addLeds<WS2812B, LED_LEFT_2_PIN, GRB>(ledsLeft2, NUM_LEDS);
  FastLED.addLeds<WS2812B, LED_RIGHT_1_PIN, GRB>(ledsRight1, NUM_LEDS);
  FastLED.addLeds<WS2812B, LED_RIGHT_2_PIN, GRB>(ledsRight2, NUM_LEDS);

  // 設定亮度 (0~255)，測試時建議先設 100 避免電流過大燒毀或供電不足
  FastLED.setBrightness(100); 

  // 將所有燈條的顏色設定為白色 (你也可以改成 CRGB::Red, CRGB::Blue 等)
  fill_solid(ledsLeft1, NUM_LEDS, CRGB::White);
  fill_solid(ledsLeft2, NUM_LEDS, CRGB::White);
  fill_solid(ledsRight1, NUM_LEDS, CRGB::White);
  fill_solid(ledsRight2, NUM_LEDS, CRGB::White);

  // 將訊號送出，燈條這時候才會亮
  FastLED.show();
}

void loop() {
  // 恆亮測試，loop 裡面不需要做任何事
}