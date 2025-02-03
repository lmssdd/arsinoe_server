#!/usr/bin/env bash

# Consider running these two commands separately
# Do a reboot before continuing.
apt update
apt upgrade -y

apt install zsh
sh -c "$(curl -fsSL https://raw.github.com/robbyrussell/oh-my-zsh/master/tools/install.sh)"

# Install some OS dependencies:
sudo apt-get install -y -q build-essential git unzip zip nload tree
sudo apt-get install -y -q python3-pip python3-dev python3-venv

# Install Redis
sudo apt install redis-server
# sudo nano /etc/redis/redis.conf
# change "supervised no" to "supervised systemd"
systemctl restart redis.service

# Stop the hackers
sudo apt install fail2ban -y

ufw allow 22
ufw allow 80
ufw allow 443
ufw enable


apt install acl -y
useradd -M apiuser
usermod -L apiuser
setfacl -m u:apiuser:rwx /apps/logs/arsinoe_server

# Web app file structure
mkdir /apps
chmod 777 /apps
mkdir /apps/logs
mkdir /apps/logs/arsinoe_server
mkdir /apps/logs/arsinoe_server/app_log
cd /apps

# Create a virtual env for the app.
cd /apps
python3 -m venv venv
source /apps/venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install --upgrade httpie glances
pip install --upgrade gunicorn uvloop httptools

# clone the repo:
cd /apps
git clone https://github.com/lmssdd/arsinoe_server app_repo/arsinoe_server

# Setup the web app:
cd /apps/app_repo/arsinoe_server
pip install -r requirements.txt

# Copy and enable the daemon
cp /apps/app_repo/arsinoe_server/server/units/arsinoe_server.service /etc/systemd/system/

systemctl start arsinoe_server
systemctl status arsinoe_server
systemctl enable arsinoe_server

# Setup the public facing server (NGINX)
apt install nginx

# CAREFUL HERE. If you are using default, maybe skip this
rm /etc/nginx/sites-enabled/default

cp /apps/app_repo/arsinoe_server/server/nginx/arsinoe_server.nginx /etc/nginx/sites-enabled/
update-rc.d nginx enable
service nginx restart

# DA COMPLETARE UNA VOLTA DEFINITO IL DOMINIO
# Optionally add SSL support via Let's Encrypt:
# https://www.digitalocean.com/community/tutorials/how-to-secure-nginx-with-let-s-encrypt-on-ubuntu-18-04

add-apt-repository ppa:certbot/certbot
apt install python3-certbot-nginx
certbot --nginx -d arsinoe_server.arsinoe.eu