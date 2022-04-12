# neurolibre-data-api
Source code (nginx, systemctl and python-flask) for http://neurolibre-data.conp.cloud/
Authentification is needed.

## Nginx
http://neurolibre-data.conp.cloud (test)
http://neurolibre-data-prod.conp.cloud (prod)

[Nginx](https://www.nginx.com/) gives access to the server cached [neurolibre books](https://github.com/neurolibre/neurolibre-books) (both for downloading, and previewing content) and the neurolibre databases collected with [Repo2Data](https://github.com/SIMEXP/Repo2Data)

## Python API endpoint
http://neurolibre-data.conp.cloud:8081/ (test)
http://neurolibre-data-prod.conp.cloud:29876/ (prod)
### python-flask
The python library [Flask](https://flask.palletsprojects.com/en/1.1.x/) is used to create the REST JSON API.
### systemctl
Spawn the python-flask deamon process as a systemd service.
### debugging
```
journalctl -u neurolibre-data-api.service
```

## Future developments
1. Secure over https
2. Include the neurolibre datasets in the API
3. Deploy the file server and api pods inside the k8s cluster