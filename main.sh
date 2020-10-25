#/bin/bash

while true; do
    pkill task01.py
    ./task01.py &
    sleep 600
done
