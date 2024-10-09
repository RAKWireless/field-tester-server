Python Field Tester Server
==========================

The Field Tester Server is a service to process and forward the coverage data for RAK10701 Field Tester or compatible devices. It's an implementation of Paul Pinault [backend service](https://github.com/disk91/WioLoRaWANFieldTester/blob/master/doc/DEVELOPMENT.md).

This folder contains a python script that fetches the data form the Field Tester device directly from your LNS via MQTT, processes it and returns it as a downlink also via MQTT.

## Configuration

The script gets the configuration information from a `config.yml` file in the same folder. You have a template for that file in the `config.yml.sample` file. This configuration file has the following options:

* mqtt section
    * server: IP or hostname of the MQTT broker to connect to
    * port: port of the MQTT server (defaults to 1883)
    * username: username to use in the MQTT connection
    * password: password to use in the MQTT connection
    * topic: topic to subscribe to (defaults to `v3/+/devices/+/up` for TTS) 
* logging section
    * level: logging level (10:debug, 20:info, 30:warning, 40:error)
* parser section
    * type: parser to use to decode the incomming JSON data (`TheThingsStack_v3` or `ChirpStack_v3+`)

## Usage

### Python virtual environment 

The recommended way to run the script is by using a virtual environment to install the dependencies in `requirements.txt`. We have provided a custom `Makefile` to help you run it in an isolated python environment by:

```
make init
make run
```

You only need to run the `make init` the first time.

### Docker

You can also use docker to run the service isolated from your system. We have provided custom `Dockerfile` and `docker-compose.yml` files for this. Please check the `docker-compose.yml` file for an example on the different ways to configure the service (mount a `config.yml` file or use environment variables).

```
docker compose build
docker compose up
```

## Contribute

There are several ways to contribute to this project. You can [report](http://github.com/rakwireless/field-tester-server/issues) bugs or [ask](http://github.com/rakwireless/field-tester-server/issues) for new features directly on GitHub.
You can also submit your own new features of bug fixes via a [pull request](http://github.com/rakwireless/field-tester-server/pr).

## License

This project is licensed under [Apache 2.0](http://www.apache.org/licenses/LICENSE-2.0) license.
