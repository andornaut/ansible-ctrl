# ansible-workstation

Provision a workstation with Ansible.

## Getting started

Requirements:

* Ubuntu >=16.04,<=17.10
* [Ansible](https://www.ansible.com/) >= 2.4.0
* [Make](https://www.gnu.org/software/make/)


## Usage

```
make letsencrypt
make rsnapshot
make upgrade
make websites
make workstation
make zoneminder
```

## Example `hosts` file

hosts

```
localhost ansible_connection=local

[rsnapshot]
localhost

[upgrade]
localhost

[webservers]
localhost

[zoneminder]
localhost
```
