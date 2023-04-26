# --------------------------------------------------------------------
# Implementation of Paul's (@disk91) field tester server in Python3
# --------------------------------------------------------------------

import os
import sys
import time
import flatdict
import yaml
import logging
import json
import base64
import binascii
import math

from yaml.loader import SafeLoader
from paho.mqtt.client import Client

class Config():

    _data = {}

    def __init__(self):
        try:
            with open("config.yml", "r") as f:
                self._data =  flatdict.FlatDict(yaml.load(f, Loader=SafeLoader), delimiter='.')
        except FileNotFoundError: 
            None

    def get(self, name, default=None):
        env_name = name.upper().replace('.', '_').replace('-', '_')
        value = os.environ.get(env_name)
        if value:
            return value
        return self._data.get(name, default)
  

class MQTTClient(Client):

    MQTTv31 = 3
    MQTTv311 = 4
    MQTTv5 = 5

    def __init__(self, broker="localhost", port=1883, username=None, password=None, userdata=None):

        def connect_callback_default(client, userdata, flags, rc):
            if rc == 0:
                logging.debug("[MQTT] Connected to MQTT Broker!")

        def subscribe_callback_default(client, userdata, mid, granted_qos):
            logging.debug("[MQTT] Subscribed")

        def disconnect_callback_default(client, userdata, rc):
            logging.debug("[MQTT] Disconnected from MQTT Broker!")

        Client.__init__(self, 
            client_id = "",
            clean_session = None,
            userdata = userdata,
            protocol = self.MQTTv311,
            transport = "tcp",
            reconnect_on_failure = True
        )

        self.on_connect = connect_callback_default
        self.on_disconnect = disconnect_callback_default
        self.on_subscribe = subscribe_callback_default
        if username and password:
            self.username_pw_set(username, password)
        self.connect(broker, port)

    def start(self):
        self.loop_start()


EARTH_RADIUS = 6371000

def degreesToRadians(degrees):
    return degrees * (math.pi / 180)

def radiansToDegrees(radians):
    return radians * (180 / math.pi)

def angularDistance(location1, location2):
    location1_latitude_radians = degreesToRadians(location1.get('latitude'))
    location2_latitude_radians = degreesToRadians(location2.get('latitude'))
    return math.acos(
        math.sin(location1_latitude_radians) * math.sin(location2_latitude_radians) +
        math.cos(location1_latitude_radians) * math.cos(location2_latitude_radians) * 
            math.cos(degreesToRadians(abs(location1.get('longitude') - location2.get('longitude'))))
    )

def circleDistance(location1, location2):
    return EARTH_RADIUS * angularDistance(location1, location2);


MAX_DISTANCE=1e6
MIN_DISTANCE=0
MAX_RSSI=200
MIN_RSSI=-200

def process(data, sequence_id, gateways):

    # Decode
    lonSign = -1 if ((data[0]>>7) & 0x01) else 1
    latSign = -1 if ((data[0]>>6) & 0x01) else 1
    encLat = ((data[0] & 0x3f)<<17) + (data[1]<<9) + (data[2]<<1) + (data[3]>>7)
    encLon = ((data[3] & 0x7f)<<16) + (data[4]<<8) + data[5]
    hdop = data[8]/10
    sats = data[9]

    # Send only acceptable quality of position to mappers
    if (hdop > 2) or (sats < 5):
        return false

    # Gather data
    output = {
        'latitude': latSign * (encLat * 108 + 53) / 10000000,
        'longitude': lonSign * (encLon * 215 + 107) / 10000000,
        'altitude': ((data[6]<<8) + data[7]) - 1000,
        'accuracy': (hdop * 5 + 5) / 10,
        'hdop': hdop,
        'sats': sats,
        'num_gateways': len(gateways),
        'min_distance': MAX_DISTANCE,
        'max_distance': MIN_DISTANCE,
        'min_rssi': MAX_RSSI,
        'max_rssi': MIN_RSSI
    }

    for gateway in gateways:

        output['min_rssi'] = min(output['min_rssi'], gateway.get('rssi', MAX_RSSI));
        output['max_rssi'] = max(output['max_rssi'], gateway.get('rssi', MIN_RSSI));

        if 'location' in gateway:
            distance = int(circleDistance(output, gateway['location'])) 
            output['min_distance'] = min(output['min_distance'], distance)
            output['max_distance'] = max(output['max_distance'], distance)

    # Build response buffer
    output['buffer'] = [
        sequence_id % 255, # sequence_id % 255
        int(output['min_rssi'] + 200) % 255, # min(rssi) + 200
        int(output['max_rssi'] + 200) % 255, # max(rssi) + 200
        round(output['min_distance'] / 250.0) % 255, # min(distance) step 250m
        round(output['max_distance'] / 250.0) % 255, # max(distance) step 250m
        output['num_gateways'] % 255 # number of gateways
    ]

    return output

def parser_tts3(config, topic, payload):

    # Parse payload
    try:
        payload = json.loads(payload)
    except:
        logging.error("[TTS3] Decoding message has failed")
        return [False, False]

    # Check structure
    if 'uplink_message' not in payload:
        return [False, False]

    # Get port
    port = payload['uplink_message']['f_port']
    if port != 1:
        return [False, False]

    # Get attributes
    sequence_id = payload['uplink_message']['f_cnt']
    gateways = payload['uplink_message']['rx_metadata']
    data = base64.b64decode((payload['uplink_message']['frm_payload']))
    logging.debug("[TTS3] Received: 0x%s" % binascii.hexlify(data).decode('utf-8'))
    
    # Process the data
    data = process(data, sequence_id, gateways)
    if not data:
        return [False, False]
    logging.debug("[TTS3] Processed: %s" % data)

    # Get topic
    topic = topic.replace('/up', '/down/replace')

    # Build downlink
    downlink = {
        'downlinks': [{
            'f_port': 2,
            'frm_payload': base64.b64encode(bytes(data['buffer'])).decode('utf-8'),
            'priority': 'HIGH'
        }]
    }

    # Return topic and payload
    return [topic, json.dumps(downlink)]

def parser_cs34(config, topic, payload):

    # Parse payload
    try:
        payload = json.loads(payload)
    except:
        logging.error("[CS34] Decoding message has failed")
        return [False, False]

    # Chirpstack version
    version = 4 if 'deviceInfo' in payload else 3
    logging.debug("[CS34] ChirpStack version %d payload" % version)

    # Get port
    port = payload.get('fPort', 0)
    if port != 1:
        return [False, False]

    # Get attributes
    sequence_id = payload['fCnt']
    gateways = payload['rxInfo']
    data = base64.b64decode((payload['data']))
    logging.debug("[CS34] Received: 0x%s" % binascii.hexlify(data).decode('utf-8'))
    
    # Process the data
    data = process(data, sequence_id, gateways)
    if not data:
        return [False, False]
    logging.debug("[CS34] Processed: %s" % data)

    # Get topic
    topic = topic.replace('/event/up', '/command/down')

    # Build downlink
    downlink = {    
        'confirmed': False,
        'fPort': 2,
        'data': base64.b64encode(bytes(data['buffer'])).decode('utf-8')
    }
    if version == 4:
        downlink['devEui'] = payload['deviceInfo']['devEui']

    # Return topic and payload
    return [topic, json.dumps(downlink)]

def main():

    # load configuration file
    config = Config()

    # set logging level based on settings (10=DEBUG, 20=INFO, ...)
    level=config.get("logging.level", logging.DEBUG)
    logging.basicConfig(format='[%(asctime)s] %(message)s', level=level)
    logging.debug("[MAIN] Setting logging level to %d" % level)

    # configure parser
    parser = False
    parser_type = config.get('parser.type', 'TheThingsStack_v3')
    if parser_type == 'TheThingsStack_v3':
        parser = parser_tts3
        logging.debug("[MAIN] Using The Things Stack v3 parser")
    elif parser_type == 'ChirpStack_v3+':
        parser = parser_cs34
        logging.debug("[MAIN] Using ChirpStack v3+ parser")
    else:
        logging.debug("[MAIN] Unknown parser type %s" % parser_type)
        sys.exit(1)

    def mqtt_on_message(client, userdata, msg):
        payload = msg.payload.decode('utf-8')
        logging.debug("[MQTT] Received for %s" % msg.topic)
        (topic, payload) = parser(config, msg.topic, payload)
        if topic:
            logging.debug("[MQTT] Topic: %s" % topic)
            logging.debug("[MQTT] Payload: %s" % payload)
            mqtt_client.publish(topic, payload)


    mqtt_client = MQTTClient(
        config.get('mqtt.server', 'locahost'), 
        int(config.get('mqtt.port', 1883)),
        config.get('mqtt.username'),
        config.get('mqtt.password')
    )
    mqtt_client.on_message = mqtt_on_message
    mqtt_client.subscribe(config.get('mqtt.topic', 'v3/+/devices/+/up'))
    mqtt_client.start()

    while (True):
        time.sleep(0.01) 

if (__name__ == '__main__'): 
    main()