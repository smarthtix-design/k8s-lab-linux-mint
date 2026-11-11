# k8s-lab-linux-mint
Local Kubernetes + Docker practice lab for Linux Mint (Ubuntu-based), built to run on low-spec hardware (4 GB RAM friendly) using kind (Kubernetes in Docker)

k8s_lab_setup.py installs and validates the tools needed for the lab:

Tool	Purpose
Docker Engine	Container runtime (kind nodes run as containers)
kubectl	Kubernetes CLI
kind	Creates local Kubernetes clusters inside Docker

It does not create clusters, nodes or pods. Cluster creation comes as a separate step.

Requirements
Linux Mint 21.x / 22.x (or any Ubuntu-based distro)
Python 3.8+
sudo access and internet connection
4 GB RAM minimum
Usage

Run as a normal user (not root):
