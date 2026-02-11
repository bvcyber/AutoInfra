#!/bin/bash

set -e
export DEBIAN_FRONTEND=noninteractive

LOGFILE="/var/log/kali-provisioning.log"
exec > >(tee -a "$LOGFILE") 2>&1

apt-get update
apt-get upgrade -y

apt-get install -y kali-desktop-xfce kali-system-gui xserver-xorg xfce4 xfce4-goodies
apt-get install -y kali-linux-default
apt-get install -y docker.io docker-compose rdesktop freerdp3-x11

mkdir -p /opt/bloodhoundce
wget https://github.com/SpecterOps/bloodhound-cli/releases/latest/download/bloodhound-cli-linux-amd64.tar.gz -O /opt/bloodhoundce/bloodhound-cli-linux-amd64.tar.gz
tar -xf /opt/bloodhoundce/bloodhound-cli-linux-amd64.tar.gz -C /opt/bloodhoundce
/opt/bloodhoundce/bloodhound-cli install
/opt/bloodhoundce/bloodhound-cli config get default_password > /opt/bloodhoundce/admin-password.txt