# ansible-workstation

Provision a workstation using Ansible.

## Requirements

* [Ansible](https://www.ansible.com/) >= 2.4.2
* [Make](https://www.gnu.org/software/make/)
* Ubuntu >= 16.04

## Usage

```
make letsencrypt
make rsnapshot
make upgrade
make websites
make workstation
make zoneminder
```

The `make workstation` target will run the [workstation](./workstation.yml) playbook.
This playbook will prompt you to choose which of its roles to include.

## Example Ansible `hosts` file

```
localhost ansible_connection=local

[upgrade]
localhost
example.com
```

## NAS

### Creating a BTRFS raid array of LUKS-encrypted devices



## Related projects

* [ansible-role-base](https://github.com/andornaut/ansible-role-base)
* [ansible-role-bspwm](https://github.com/andornaut/ansible-role-bspwm)
* [ansible-role-docker](https://github.com/andornaut/ansible-role-docker)
* [ansible-role-letsencrypt](https://github.com/andornaut/ansible-role-letsencrypt)
* [ansible-role-nginx](https://github.com/andornaut/ansible-role-nginx)
* [ansible-role-rsnapshot](https://github.com/andornaut/ansible-role-rsnapshot)
* [ansible-role-zoneminder](https://github.com/andornaut/ansible-role-zoneminder)
