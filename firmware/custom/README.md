# Custom release 0.3.6.0 — development status

**There is no custom firmware binary in this directory.**

The version number is reserved for the proposed mowing behavior. The working implementation is an offline Python geometric planner under [src/planner](../../src/planner). It has not been ported into a buildable ESP-IDF application, integrated into the vendor controller, or flashed onto a mower.

The [Wi-Fi uploader](../../src/uploader) is a separate program. It sends the version found inside the selected image. It does not insert the new planner into that image, change the embedded version, or convert Python into ESP32 firmware.

To produce a real release, the work still needs a verified hardware interface, localization/map adapter, constrained turn trajectories, complete coverage/edge handling, original protective behavior, a build and recovery strategy, update-security compatibility, and hardware acceptance. See the root README's development-status and validation sections.
