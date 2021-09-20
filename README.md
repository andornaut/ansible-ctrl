# ansible-workstation

Provision workstations and servers using [Ansible](https://www.ansible.com/).

## Requirements

* [Ansible](https://www.ansible.com/) >= 2.8.0
* [Make](https://www.gnu.org/software/make/)
* Ubuntu >= 18.04

Create a file in the project root named "hosts":
```
example ansible_connection=local ansible_host=example.com ansible_user=andornaut ansible_python_interpreter=/usr/bin/python3

[upgrade]
example
```

## Usage

```bash
make homeassistant-frigate
make rsnapshot
make upgrade
make webservers
make workstation
```

The `make workstation` target will run the [workstation](./workstation.yml) playbook.
This playbook will prompt you to choose which of its roles to include.

## Configuration

See default Ansible variables:

- [ansible-role-base](https://github.com/andornaut/ansible-role-base/blob/master/defaults/main.yml)
- [ansible-role-bspwm](https://github.com/andornaut/ansible-role-bspwm/blob/master/defaults/main.yml)
- [ansible-role-desktop](./roles/desktop/defaults/main.yml)
- [ansible-role-dev](./roles/dev/defaults/main.yml)
- [ansible-role-docker](https://github.com/andornaut/ansible-role-docker/blob/master/defaults/main.yml)
- [ansible-role-homeassistant-frigate](https://github.com/andornaut/ansible-role-homeassistant-frigate/blob/main/defaults/main.yml)
- [ansible-role-letsencrypt-nginx](https://github.com/andornaut/ansible-role-letsencrypt-nginx/blob/master/defaults/main.yml)
- [ansible-role-msmtp](./roles/msmtp/defaults/main.yml)
- [ansible-role-nas](./roles/nas/defaults/main.yml)
- [ansible-role-rsnapshot](https://github.com/andornaut/ansible-role-rsnapshot/blob/master/defaults/main.yml)

## Embedded role documentation

* [ansible-role-nas](./roles/nas/README.md)
