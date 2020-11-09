#!/usr/bin/python -u
# coding=utf-8
# "DATASHEET": http://cl.ly/ekot
# https://gist.github.com/kadamski/92653913a53baf9dd1a8
# V1.0 2020.11.08
from __future__ import print_function
import serial, struct, sys, time, subprocess, requests, bme280, Adafruit_DHT

DEBUG = 0
CMD_MODE = 2
CMD_QUERY_DATA = 4
CMD_DEVICE_ID = 5
CMD_SLEEP = 6
CMD_FIRMWARE = 7
CMD_WORKING_PERIOD = 8
MODE_ACTIVE = 0
MODE_QUERY = 1
PERIOD_CONTINUOUS = 0



def dump(d, prefix=''):
    print(prefix + ' '.join(x.encode('hex') for x in d))

def construct_command(cmd, data=[]):
    assert len(data) <= 12
    data += [0,]*(12-len(data))
    checksum = (sum(data)+cmd-2)%256
    ret = "\xaa\xb4" + chr(cmd)
    ret += ''.join(chr(x) for x in data)
    ret += "\xff\xff" + chr(checksum) + "\xab"

    if DEBUG:
        dump(ret, '> ')
    return ret

def process_data(d):
    r = struct.unpack('<HHxxBB', d[2:])
    pm25 = r[0]/10.0
    pm10 = r[1]/10.0
    checksum = sum(ord(v) for v in d[2:8])%256
    return [pm25, pm10]
    #print("PM 2.5: {} μg/m^3  PM 10: {} μg/m^3 CRC={}".format(pm25, pm10, "OK" if (checksum==r[2] and r[3]==0xab) else "NOK"))

def process_version(d):
    r = struct.unpack('<BBBHBB', d[3:])
    checksum = sum(ord(v) for v in d[2:8])%256
    print("Y: {}, M: {}, D: {}, ID: {}, CRC={}".format(r[0], r[1], r[2], hex(r[3]), "OK" if (checksum==r[4] and r[5]==0xab) else "NOK"))

def read_response():
    byte = 0
    while byte != "\xaa":
        byte = ser.read(size=1)

    d = ser.read(size=9)

    if DEBUG:
        dump(d, '< ')
    return byte + d

def cmd_set_mode(mode=MODE_QUERY):
    ser.write(construct_command(CMD_MODE, [0x1, mode]))
    read_response()

def cmd_query_data():
    ser.write(construct_command(CMD_QUERY_DATA))
    d = read_response()
    values = []
    if d[1] == "\xc0":
        values = process_data(d)
    return values

def cmd_set_sleep(sleep):
    mode = 0 if sleep else 1
    print ("Mode: "+str(mode))
    ser.write(construct_command(CMD_SLEEP, [0x1, mode]))
    read_response()

def cmd_set_alive(sleep):
    mode = 0 if sleep else 1
    ser.write(construct_command(CMD_SLEEP, [0x1, mode]))
    read_response()

def cmd_set_working_period(period):
    ser.write(construct_command(CMD_WORKING_PERIOD, [0x1, period]))
    read_response()

def cmd_firmware_ver():
    ser.write(construct_command(CMD_FIRMWARE))
    d = read_response()
    process_version(d)

def cmd_set_id(id):
    id_h = (id>>8) % 256
    id_l = id % 256
    ser.write(construct_command(CMD_DEVICE_ID, [0]*10+[id_l, id_h]))
    read_response()

def pub_mqtt(jsonrow):
    cmd = ['mosquitto_pub', '-h', MQTT_HOST, '-t', MQTT_TOPIC, '-s']
    print('Publishing using:', cmd)
    with subprocess.Popen(cmd, shell=False, bufsize=0, stdin=subprocess.PIPE).stdin as f:
        json.dump(jsonrow, f)

key = open("/boot/key","r").read()


if __name__ == "__main__":
#    while True:
        ser = serial.Serial()
        ser.port = "/dev/ttyUSB0"
        ser.baudrate = 9600
        ser.open()
        ser.flushInput()
        byte, data = 0, ""
        cmd_set_sleep(0)
        cmd_firmware_ver()
        cmd_set_working_period(PERIOD_CONTINUOUS)
        cmd_set_mode(MODE_QUERY);
        pm25=list()
        pm10=list()
        for t in range(15):
            values = cmd_query_data();
            if values is not None and len(values) == 2:
              print("PM2.5: ", values[0], ", PM10: ", values[1], "for dummy")
              time.sleep(2)
        for t in range(15):
            values = cmd_query_data();
            if values is not None and len(values) == 2:
              print("PM2.5: ", values[0], ", PM10: ", values[1])
              time.sleep(2)
              pm25.append(values[0])
              pm10.append(values[1])
        print(*pm25)
        print(*pm10)
        post_data = {'pm2' : round(sum(pm25)/len(pm25)), 'pm10' : round(sum(pm10)/len(pm10)), 'date' : time.time(), 'station_id' : '273'}

        try:
          t1,p,rh = bme280.readBME280All()
          print ("I2C Interface ")
          print ("Temperature : ", t1, "C")
          print ("Pressure : ", p, "hPa")
          print ("Humidity : ", rh, "%")
          post_data['Pressure']=p
        except:
          print("There is no i2c temperature")

        try:
            rh, t = Adafruit_DHT.read_retry(Adafruit_DHT.DHT22, 4)
            post_data['temperature']=round(t,1)
            post_data['humidity']=round(rh,1)
            print (" DHT22: ")
            print ("Temperature : ", round(t,1), "C")
            print ("Humidity : ", round(rh,1), "%")
        except:
            print("There is no DHT22 data...")
            if (t1<>''):
                post_data['temperature']=t1

        post_data['X-Device-Token']=key
        response = requests.post('https://www.metnet.hu/api/data', data = post_data)
        print(post_data)
        print(response.text)
        cmd_set_sleep(1)
        ser.close()
