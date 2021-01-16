# ansible-workstation

Provision a workstation using [Ansible](https://www.ansible.com/).

## Requirements

* [Ansible](https://www.ansible.com/) >= 2.6.0 (you can [install the latest version using pip](https://docs.ansible.com/ansible/2.5/installation_guide/intro_installation.html#latest-releases-via-pip))
* [Make](https://www.gnu.org/software/make/)
* Ubuntu >= 16.04

Create a file in the project root named "hosts":
```
localhost ansible_connection=local ansible_python_interpreter=/usr/bin/python3
```

## Usage

```bash
make rsnapshot
make upgrade
make webservers
make workstation
make zoneminder
```

The `make workstation` target will run the [workstation](./workstation.yml) playbook.
This playbook will prompt you to choose which of its roles to include.

## Configuration

See default variables:

- [ansible-role-base](https://github.com/andornaut/ansible-role-base/blob/master/defaults/main.yml)
- [ansible-role-bspwm](https://github.com/andornaut/ansible-role-bspwm/blob/master/defaults/main.yml)
- [ansible-role-desktop](./roles/desktop/defaults/main.yml)
- [ansible-role-dev](./roles/dev/defaults/main.yml)
- [ansible-role-docker](https://github.com/andornaut/ansible-role-docker/blob/master/defaults/main.yml)
- [ansible-role-letsencrypt-nginx](https://github.com/andornaut/ansible-role-letsencrypt-nginx/blob/master/defaults/main.yml)
- [ansible-role-msmtp](./roles/msmtp/defaults/main.yml)
- [ansible-role-nas](./roles/nas/defaults/main.yml)
- [ansible-role-rsnapshot](https://github.com/andornaut/ansible-role-rsnapshot/blob/master/defaults/main.yml)
- [ansible-role-zoneminder](https://github.com/andornaut/ansible-role-zoneminder/blob/master/defaults/main.yml)

## Example Ansible `hosts` file

```
localhost ansible_connection=local

[upgrade]
localhost
example.com
```

## NAS

See [roles/nas/README.md](./roles/nas/README.md).
