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
            record_deadline = time.monotonic() + FEED_REC_SECS
            time.sleep(1) # make sure this writes before we drop the feed 

        rectime=FEED_REC_SECS
        #Drop the food
        feed_drop_motor()
        rectime-=SECS_PER_SECTION  # reduce time to  wait to finish recording by time takes motor to move a section

        if recording :
            #Record a little bit
            time.sleep(max(0, record_deadline - time.monotonic()))
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


def handle_command(command):
    """Process one complete command; rec_len affects subsequent feeds only."""
    global FEED_REC_SECS, recording
    parts = command.split()
    if not parts:
        return None
    if parts[0] == 'rec_len':
        if len(parts) != 2 or not parts[1].isascii() or not parts[1].isdigit():
            return 'ERR usage: rec_len <whole seconds>'
        seconds = int(parts[1])
        # Feeding takes 1 second of lead-in plus 26 seconds of motor operation.
        if seconds < SECS_PER_SECTION + 1 or seconds > 86400:
            return f'ERR rec_len must be {SECS_PER_SECTION + 1}..86400 seconds'
        FEED_REC_SECS = seconds
        syslog.syslog(syslog.LOG_INFO, f'Feed recording length set to {seconds} seconds')
        return f'OK rec_len {seconds}'
    if command == 'f':
        feed(1)
    elif command == 'F':
        feed(2)
    elif command.startswith('S') and command[1:].strip().isdigit():
        spin_seconds(command[1:].strip())
    elif command.startswith('T') and command[1:].strip().isdigit():
        record_test(int(command[1:].strip()))
    elif command == 'R':
        recording = not recording
        syslog.syslog(syslog.LOG_INFO, f'Recording on feed: {recording}')
    else:
        return 'ERR unknown command'
    return None


def serve_connection(conn):
    # TCP reads are not message boundaries. Accept newline or connection EOF.
    pending = bytearray()
    oversized = False

    def dispatch():
        nonlocal oversized
        if oversized:
            reply = 'ERR command too long'
        else:
            try:
                reply = handle_command(pending.decode('ascii').strip())
            except UnicodeDecodeError:
                reply = 'ERR command must be ASCII'
        pending.clear()
        oversized = False
        if reply:
            syslog.syslog(syslog.LOG_INFO, reply)
            try:
                conn.sendall((reply + '\n').encode('ascii'))
            except OSError:
                pass  # Existing send-only netcat clients disconnect immediately.

    while True:
        data = conn.recv(1024)
        if not data:
            if pending or oversized:
                dispatch()
            return
        for byte in data:
            if byte == 10:
                dispatch()
            elif not oversized:
                if len(pending) >= 256:
                    oversized = True
                else:
                    pending.append(byte)


def main():
    syslog.syslog(syslog.LOG_INFO, 'Feeder control started')
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(GPIO_FEED_MOTOR, GPIO.OUT, initial=GPIO.LOW)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(('', 33333))
            server.listen(1)
            while True:
                conn, addr = server.accept()
                with conn:
                    try:
                        serve_connection(conn)
                    except (ConnectionError, TimeoutError) as error:
                        syslog.syslog(syslog.LOG_WARNING, f'Client disconnected: {error}')
    finally:
        GPIO.output(GPIO_FEED_MOTOR, 0)
        GPIO.cleanup()
        syslog.syslog(syslog.LOG_INFO, 'Feeder control terminating')


if __name__ == '__main__':
    main()
