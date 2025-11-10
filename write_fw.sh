#! /bin/bash

usbPath=$1
binaryFilePath=$2

# echo -e "TEST_VERSION\n" > $usbPath
sleep 2
stty -F $usbPath 115200
#stty -F $usbPath 54200
#stty -F $usbPath N 115200 #speed baud #; line = 0; -brkint -imaxbel
#stty -F $usbPath 115200 cs8 -parenb -cstopb -tostop clocal cread -crtscts
echo "Mandando \nTEST_REBOOT"
echo -e "\nTEST_REBOOT" > $usbPath
sleep 0.2
echo "writing"
echo -n "worldsensing" > $usbPath  && sleep 0.7 && echo -n "3" > $usbPath && sleep 1 && sx -vv --ymodem $binaryFilePath < $usbPath > $usbPath
