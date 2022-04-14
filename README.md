# neurolibre-data-api
Source code (nginx, systemctl and python-flask) for http://neurolibre-data.conp.cloud/
Authentification is needed.

## Data server
http://neurolibre-data.conp.cloud (test)

http://neurolibre-data-prod.conp.cloud (prod)

#### Environment
* Nginx: [Nginx](https://www.nginx.com/) gives access to the server cached [neurolibre books](https://github.com/neurolibre/neurolibre-books) (both for downloading, and previewing content) and the neurolibre databases collected with [Repo2Data](https://github.com/SIMEXP/Repo2Data)

#### Installation
After cloning the project, add a symbolic link to create the nginx:
```
git clone git@github.com:neurolibre/neurolibre-data-api.git
sudo ln -s /etc/nginx/conf.d/default.conf PATH/TO/REPO/neurolibre-data-api/nginx/neurolibre-data-api.config
```
You can now start the nginx process and check its status:
```
sudo service nginx restart
sudo systemctl status nginx
```

## Python API endpoint
http://neurolibre-data.conp.cloud:8081/ (test)

http://neurolibre-data-prod.conp.cloud:29876/ (prod)
#### Environment
* python-flask: The python library [Flask](https://flask.palletsprojects.com/en/1.1.x/) is used to create the REST JSON API.
* systemctl: Shoud be included by default in any linux based OS.

#### Installation
Spawn the python-flask deamon process as a systemd service.
After cloning the project, add a symbolic link to create the systemd service:
```
git clone git@github.com:neurolibre/neurolibre-data-api.git
sudo ln -s /etc/systemd/system/neurolibre-data-api.service PATH/TO/REPO/neurolibre-data-api/systemctl/neurolibre-data-api.service
```
You can now start the daemon process and check its status:
```
sudo systemctl start neurolibre-data-api
sudo systemctl status neurolibre-data-api
```
#### Update and debugging
To update the api, you just need to modify the python script `neurolibre-data-api/neurolibre-data-api.py`.
Then you can double check errors by checking the latest logs from:
```
journalctl -u neurolibre-data-api.service
```

## Future developments
1. Secure over https
2. Deploy the file server and api pods inside the k8s cluster
