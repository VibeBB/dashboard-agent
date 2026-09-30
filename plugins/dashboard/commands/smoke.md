---
description: Smoke-test a generated dashboard in Servo.
allowed-tools:
  - terminal
---

Run `dashboard smoke <contract>` through the plugin launcher. Treat WebDriver
startup, navigation, and diagnostics failures as failures; never weaken the
smoke assertions. A successful Servo smoke also saves a screenshot when the
browser supports WebDriver screenshots; screenshot failures do not change the
smoke verdict.
