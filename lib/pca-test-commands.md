# PCA Commands

This file contains the implemented PCA test commands, exemplifying how to use them. It implies that bash shell interpreter is used to process the commands.

**Note** that 'echo -e' automatically adds `\n` at the end of the command.
```bash
export USB=/dev/ttyUSB0
```

## Common commands
```bash
echo -e '\nTEST_VERSION' > $USB
echo -e '\nTEST_STM32_ID' > $USB
echo -e '\nTEST_FLASH' > $USB
echo -e '\nTEST_FLASH_ENABLE' > $USB
echo -e '\nTEST_FLASH_DISABLE' > $USB
echo -e '\nTEST_REBOOT' > $USB
echo -e '\nTEST_VIN' > $USB
echo -e '\nTEST_TEMP_HUM' > $USB
echo -e '\nTEST_LOWPOW' > $USB
echo -e '\nTEST_FULLPOW_DISABLE' > $USB
echo -e '\nTEST_FULLPOW' > $USB
echo -e '\nTEST_LP_ACC' > $USB
echo -e '\nTEST_LORA_ENABLE' > $USB
echo -e '\nTEST_LORA_DISABLE' > $USB
echo -e '\nTEST_LORA_TONE FREQ PWR TIME' > $USB
echo -e '\nTEST_LORA_TX FREQ PWR SF' > $USB
echo -e '\nTEST_LORA_TX_CONT FREQ PWR SF' > $USB
echo -e '\nTEST_LORA_RX FREQ SF TIME' > $USB
echo -e '\nTEST_LORA_ID' > $USB
echo -e '\nTEST_BLE_ENABLE' > $USB
echo -e '\nTEST_BLE_DISABLE' > $USB
echo -e '\nTEST_BLE_FW' > $USB
echo -e '\nTEST_BLE_ID' > $USB
echo -e '\nTEST_BLE_START_ADV' > $USB
echo -e '\nTEST_BLE_STOP_ADV' > $USB
echo -e '\nTEST_BLE_MODULATED_PN9 CHANNEL POWER PACKET_LENGTH' > $USB
echo -e '\nTEST_BLE_MODULATED_PRBS9 CHANNEL POWER PACKET_LENGTH' > $USB
echo -e '\nTEST_BLE_UNMODULATED CHANNEL POWER PACKET_LENGTH' > $USB
echo -e '\nTEST_BLE_RX CHANNEL' > $USB
echo -e '\nTEST_BLE_STOP'  > $USB
```

## TILT360 specific commands
```bash
echo -e '\nTEST_MAG_MMC' > $USB
echo -e '\nTEST_HP_ACC' > $USB
```

## GNSS specific commands
```bash
echo -e '\nTEST_MAG_MMC' > $USB
echo -e '\nTEST_HP_ACC' > $USB
echo -e '\nTEST_GNSS_ENABLE' > $USB
echo -e '\nTEST_GNSS_DISABLE' > $USB
echo -e '\nTEST_GNSS_POSITION TIMEOUT' > $USB
echo -e '\nTEST_GNSS_FW_VERSION' > $USB
echo -e '\nTEST_GNSS_BCK_H' > $USB
echo -e '\nTEST_GNSS_BCK_L' > $USB
echo -e '\nTEST_BAROMETER' > $USB
```

## VW specific commands
```bash
echo -e '\nTEST_BAROMETER' > $USB
echo -e '\nTEST_VW6_VW NO_CHANNELS' > $USB
echo -e '\nTEST_VW2_VW NO_CHANNELS' > $USB
echo -e '\nTEST_VW6_TH NO_CHANNELS' > $USB
echo -e '\nTEST_VW2_TH NO_CHANNELS' > $USB
```

