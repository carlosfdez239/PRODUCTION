#!/bin/bash

control_c()
# run if user hits control-c
{
    echo -en "\nExiting ***\n"
    kill $$
}

usage() {
    echo "Usage: $0 <tty_of_the_mote> [-l] [-s IP]"
    echo "       -s: instead of using tty_of_the_mote, connect through a socket to the server on IP."
    echo "           In this case, the tty_of_the_mote is used to deduce the port of the connection."
    echo "Example: $0 /dev/ttyUSB0 -s 192.168.4.120"
    exit 1
}

# trap keyboard interrupt (control-c)
trap control_c SIGINT

if [ $# -lt 1 ]; then
    usage
fi

if [[ $# -eq 2 && "$2" != "-l" ]]; then
    usage
fi

if [[ $# -eq 3 && "$2" != "-s" ]]; then
    usage
fi

if [[ $# -eq 5 && ("$2" != "-l" || "$3" != "-s") ]]; then
    usage
fi

while :
do
    /usr/bin/env python3.9 -u ls_serial_view.py "$@" 2>/dev/null
    sleep 1
done


