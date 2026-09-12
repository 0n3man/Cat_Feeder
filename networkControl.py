#!/usr/bin/python3
# Use PCA9685 PWM servo/LED controller library to control servos
# Author: Tony DiCola
# License: Public Domain
from __future__ import division
import time
import sys
import socket
import RPi.GPIO as GPIO
import random
import datetime
import math
import syslog


syslog.openlog(ident="networkControl", logoption=syslog.LOG_PID, facility=syslog.LOG_USER)

GPIO.setmode(GPIO.BCM)

# Uncomment to enable debug output.
#import logging
#logging.basicConfig(level=logging.DEBUG)

feed_method='M'  # S for servo, anything else for motor
SECS_PER_SECTION=26  #  NUM of seconds it takes to move a section

#FEED_REC_SECS=25
FEED_REC_SECS=300

recording = False
recording = True

GPIO_FEED_MOTOR = 17


def feed_drop_motor():

    #print("Power on for feed motor")
    syslog.syslog(syslog.LOG_INFO, "Power on feed motor")
    GPIO.output(GPIO_FEED_MOTOR, 1) # turn motor on
    time.sleep(SECS_PER_SECTION)  #  sleep time it takes to move a section
    GPIO.output(GPIO_FEED_MOTOR, 0) # turn motor on
    #print("Power off for feed motor")
    syslog.syslog(syslog.LOG_INFO, "Power off feed motor")


def feed( sections ):

    #print("Time to feed")
    syslog.syslog(syslog.LOG_INFO, "Got Feed command")
    # open FIFO used to start recording if need be
    with open('/var/www/html/FIFO1', 'a') as f:

        if recording :
            syslog.syslog(syslog.LOG_INFO, "Writting 1 to start recording")
            #print("Writting 1 to start recording")
            # Tell raspimjpeg scheduler to start recording
            f.write('1')
            f.flush()
            time.sleep(1) # make sure this writes before we drop the feed 

        rectime=FEED_REC_SECS
        #Drop the food
        feed_drop_motor()
        rectime-=SECS_PER_SECTION  # reduce time to  wait to finish recording by time takes motor to move a section

        if recording :
            #Record a little bit
            time.sleep(rectime)
            #print("Writting 0 to stop recording")
            syslog.syslog(syslog.LOG_INFO, "Writting 0 to stop recording")
            # Tell raspimjpeg scheduler to stop recording
            f.write('0')
            f.flush()

        f.close()


def record_test( record_time ):

    syslog.syslog(syslog.LOG_INFO, "Got record test cmd")
    # open FIFO used to start recording if need be
    with open('/var/www/html/FIFO1', 'a') as f:

        if recording :
            syslog.syslog(syslog.LOG_INFO, "Writting 1 to start recording")
            #print("Writting 1 to start recording")
            # Tell raspimjpeg scheduler to start recording
            f.write('1')
            f.flush()

            #Record a little bit
            time.sleep( record_time )
            #print("Writting 0 to stop recording")
            syslog.syslog(syslog.LOG_INFO, "Writting 0 to stop recording")
            # Tell raspimjpeg scheduler to stop recording
            f.write('0')
            f.flush()

        f.close()



def spin_seconds( seconds_as_bytes ):

    seconds_as_int = int(seconds_as_bytes)

    #print("Power on for feed motor for: ", seconds_as_int)
    syslog.syslog(syslog.LOG_INFO, "Power on feed motor")
    GPIO.output(GPIO_FEED_MOTOR, 1) # turn motor on
    time.sleep(seconds_as_int)  #  sleep time it takes to move a section
    GPIO.output(GPIO_FEED_MOTOR, 0) # turn motor on
    syslog.syslog(syslog.LOG_INFO, "Power off feed motor")
    #print("Power off for feed motor")


# -- Main ----
#print( "Feeder control started" )
syslog.syslog(syslog.LOG_INFO, "Feeder control started")

#for arg in sys.argv[1:]:
#    print( arg )

GPIO.setup(GPIO_FEED_MOTOR, GPIO.OUT)
GPIO.output(GPIO_FEED_MOTOR, 0)
sys.stdout.flush()

HOST = ''                 # Symbolic name meaning all available interfaces
PORT = 33333              # Arbitrary non-privileged port
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((HOST, PORT))
    s.listen(1)

    try:
        while True:
            conn, addr = s.accept()
            with conn:
                #print('Connected by', addr)
                while True:
                    data = conn.recv(1024)
                    if not data: break
                    #print('Data: ',data)

                    if chr(data[0]) == 'f':
                        feed(1)
                    elif chr(data[0]) == 'F':
                        feed(2)
                    elif chr(data[0]) == 'S':
                        spin_time = data[1:2]
                        spin_seconds(spin_time)
                    elif chr(data[0]) == 'T':
                        record_time = int(data[1:2])
                        record_test(record_time)
                    elif chr(data[0]) == 'R':
                        if recording :
                            #print("Disable recording on feed")
                            syslog.syslog(syslog.LOG_INFO, "Disable recording on feed request")
                            recording = False
                        else:
                            #print("Enable recording on feed")
                            syslog.syslog(syslog.LOG_INFO, "Enable recording on feed request")
                            recroding = True

                conn.close()
                sys.stdout.flush()
    finally:
        GPIO.output(GPIO_FEED_MOTOR, 0)
        GPIO.cleanup()
        #print( "Feeder control terminating" )
        syslog.syslog(syslog.LOG_INFO, "Feeder control terminating")
