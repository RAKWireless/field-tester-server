/* 
 *
 *  Copyright (c) 2023 RAKwireless
 *
 *  Licensed under the Apache License, Version 2.0 (the "License");
 *  you may not use this file except in compliance with the License.
 *  You may obtain a copy of the License at
 *
 *  http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software
 *  distributed under the License is distributed on an "AS IS" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions and
 *  limitations under the License.
 *
 */

module.exports = function(RED) {

    "use strict";

    // --------------------------------------------------------------------
    // Distance calculation
    // --------------------------------------------------------------------

    const EARTH_RADIUS = 6371000;

    function degreesToRadians(degrees) {
        return degrees * (Math.PI / 180);
    }

    function radiansToDegrees(radians) {
        return radians * (180 / Math.PI);
    }

    function angularDistance(location1, location2) {
        const location1_latitude_radians = degreesToRadians(location1.latitude);
        const location2_latitude_radians = degreesToRadians(location2.latitude);
        return Math.acos(
            Math.sin(location1_latitude_radians) * Math.sin(location2_latitude_radians) +
            Math.cos(location1_latitude_radians) * Math.cos(location2_latitude_radians) * 
                Math.cos(degreesToRadians(Math.abs(location1.longitude - location2.longitude)))
        );
    }

    function circleDistance(location1, location2) {
        return EARTH_RADIUS * angularDistance(location1, location2);
    }

    // --------------------------------------------------------------------
    // Data process
    // --------------------------------------------------------------------

    function ftdProcess(bytes, sequence_id, gateways) {

        // decode bytes    
        var lonSign = (bytes[0]>>7) & 0x01 ? -1 : 1;
        var latSign = (bytes[0]>>6) & 0x01 ? -1 : 1;
        var encLat = ((bytes[0] & 0x3f)<<17)+(bytes[1]<<9)+(bytes[2]<<1)+(bytes[3]>>7);
        var encLon = ((bytes[3] & 0x7f)<<16)+(bytes[4]<<8)+bytes[5];
        var hdop = bytes[8]/10;
        var sats = bytes[9];

        // send only acceptable quality of position to mappers
        if ((hdop > 2) || (sats < 5)) return false;

        // create decoded data downlink
        var data = {};
        data.latitude = latSign * (encLat * 108 + 53) / 10000000;
        data.longitude = lonSign * (encLon * 215 + 107) / 10000000;  
        data.altitude = ((bytes[6]<<8)+bytes[7])-1000;
        data.accuracy = (hdop*5+5)/10;
        data.hdop = hdop;
        data.sats = sats;
                
        // build gateway data
        data.num_gateways = gateways.length;
        data.min_distance = 1e6;
        data.max_distance = 0;
        data.min_rssi = 200;
        data.max_rssi = -200;
        gateways.forEach(function(gateway) {

            if (gateway.rssi < data.min_rssi) data.min_rssi = gateway.rssi;
            if (gateway.rssi > data.max_rssi) data.max_rssi = gateway.rssi;
            if (gateway.location) {
                var distance = parseInt(circleDistance(data, gateway.location)); 
                if (distance < data.min_distance) data.min_distance = distance;
                if (distance > data.max_distance) data.max_distance = distance;
            }
            
        });

        // build response buffer
        data.buffer = Buffer.from([
            sequence_id % 255, // sequence_id % 255
            parseInt(data.min_rssi + 200, 10) % 255, // min(rssi) + 200
            parseInt(data.max_rssi + 200, 10) % 255, // max(rssi) + 200
            Math.round(data.min_distance / 250.0) % 255, // min(distance) step 250m
            Math.round(data.max_distance / 250.0) % 255, // max(distance) step 250m
            data.num_gateways % 255 // number of gateways
        ])

        return data;

    }

    function parser_raw(msg) {

        // get raw input
        var bytes = msg.payload.bytes || [];
        if (bytes.length != 10) return null;
        var uplink_counter = msg.payload.uplink_counter || 0;
        var gateways = msg.payload.gateways || [];
        
        // get response
        msg.payload = ftdProcess(bytes, uplink_counter, gateways);
        
        return msg;

    }

    function parser_tts3(msg) {

        // filter valid message type
        if (!msg.payload.uplink_message) return null;

        // avoid sending downlink ACK to integration
        if (msg.payload.uplink_message.f_port != 1) return null;

        // get raw input
        var bytes = Buffer.from(msg.payload.uplink_message.frm_payload, 'base64');
        var sequence_id = msg.payload.uplink_message.f_cnt;
        var gateways = msg.payload.uplink_message.rx_metadata;
        var app_id = msg.payload.end_device_ids.application_ids.application_id;
        var dev_id = msg.payload.end_device_ids.device_id;

        // get response
        var data = ftdProcess(bytes, sequence_id, gateways);
        if (data == null) return null;

        // build response for TTN
        msg.data = data;
        msg.topic = msg.topic.replace('/up', '/down/replace');
        msg.payload = {
            "downlinks": [{
                "f_port": 2,
                "frm_payload": data.buffer.toString('base64'),
                "priority": "HIGH"
            }]
        }

        return msg;

    }

    function parser_cs34(msg) {
        
        // avoid sending downlink ACK to integration
        if (msg.payload.fPort != 1) return null;

        // get version
        var version = ('deviceInfo' in msg.payload) ? 4 : 3;

        // get raw input
        var bytes = Buffer.from(msg.payload.data, 'base64');
        var sequence_id = msg.payload.fCnt;
        var gateways = msg.payload.rxInfo;
        var dev_eui = (version == 4) ? msg.payload.deviceInfo.devEui : msg.payload.devEui;

        // get response
        var data = ftdProcess(bytes, sequence_id, gateways);
        if (data == null) return null;

        // build response for TTN
        msg.data = data;
        msg.topic = msg.topic.replace('/event/up', '/command/down');
        msg.payload = {
            "confirmed": false,
            "fPort": 2,
            "data": data.buffer.toString('base64')
        }
        if (version == 4) {
            msg.payload.devEui = dev_eui;
        }

        return msg;

    }


    // --------------------------------------------------------------------
    // Main
    // --------------------------------------------------------------------

    function field_tester_service(config) {

        RED.nodes.createNode(this, config);

        var node = this;

        this.name = config.name || "";
        this.parser = config.parser || "tts3";

        this.on("input", function(msg) {

            // process data
            if (this.parser == 'raw') {
                msg = parser_raw(msg);
            } else if (this.parser == 'tts3') {
                msg = parser_tts3(msg);
            } else if (this.parser == 'cs34') {
                msg = parser_cs34(msg);
            } else {
                return null;
            }
            
            // send data
            node.send(msg);
        
        });

    };

    RED.nodes.registerType("field_tester_service", field_tester_service);

};