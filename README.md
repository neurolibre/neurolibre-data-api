# neurolibre-data-api
Source code (nginx, systemctl and python-flask) for http://neurolibre-data.conp.cloud/

## Nginx
For serving neurolibre databases

## Python API endpoint
http://neurolibre-data.conp.cloud:8081/
### python-flask
The python library [Flask](https://flask.palletsprojects.com/en/1.1.x/) is used to create the REST JSON API.
### systemctl
Spawn the python-flask deamon process as a systemd service.
