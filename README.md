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

### Creating a BTRFS raid1 array of LUKS-encrypted devices

- [Btrfs Multi Device Dmcrypt](http://marc.merlins.org/perso/btrfs/post_2014-04-27_Btrfs-Multi-Device-Dmcrypt.html)
- [Cryptsetup](https://gitlab.com/cryptsetup/cryptsetup)
- [Using Btrfs with Multiple Devices](https://btrfs.wiki.kernel.org/index.php/Using_Btrfs_with_Multiple_Devices)

```bash
# Create a keyfile
head -c 256 /dev/random > keyfile

# Create LUKS devices
device=/dev/...
cryptsetup luksFormat ${device}

# Add a key-file (which can be used instead of the passphrase created above)
keyfile=/home/...
cryptsetup luksAddKey ${device} ${keyfile}

# Map the container to /dev/mapper/left
cryptsetup luksOpen --key-file ${keyfile} ${device} left

# Create BTRFS raid1 array
mkfs.btrfs -m raid1 -d raid1 /dev/mapper/left /dev/mapper/right

# Mount the array
mount \
    -t btrfs /dev/mapper/left \
    -o device=/dev/mapper/left,device=/dev/mapper/right \
    /media/nas

btrfs filesystem show /media/nas
```

## Related projects

* [ansible-role-base](https://github.com/andornaut/ansible-role-base)
* [ansible-role-bspwm](https://github.com/andornaut/ansible-role-bspwm)
* [ansible-role-docker](https://github.com/andornaut/ansible-role-docker)
* [ansible-role-letsencrypt](https://github.com/andornaut/ansible-role-letsencrypt)
* [ansible-role-nginx](https://github.com/andornaut/ansible-role-nginx)
* [ansible-role-rsnapshot](https://github.com/andornaut/ansible-role-rsnapshot)
* [ansible-role-zoneminder](https://github.com/andornaut/ansible-role-zoneminder)
