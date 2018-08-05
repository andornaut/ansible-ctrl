# ansible-workstation

Provision a workstation using [Ansible](https://www.ansible.com/).

## Requirements

* [Ansible](https://www.ansible.com/) >= 2.5.0 (you can [install the latest version using pip](https://docs.ansible.com/ansible/2.5/installation_guide/intro_installation.html#latest-releases-via-pip)
* [Make](https://www.gnu.org/software/make/)
* Ubuntu >= 16.04

## Usage

```
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
- [ansible-role-nas](./roles/nas/defaults/main.yml)
- [ansible-role-rsnapshot](https://github.com/andornaut/ansible-role-rsnapshot/blob/master/defaults/main.yml)
- [ansible-role-zoneminder](https://github.com/andornaut/ansible-role-zoneminder)

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
device=/dev/disk/by-id/...
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

Mounting [a degraded array](https://btrfs.wiki.kernel.org/index.php/Using_Btrfs_with_Multiple_Devices#Replacing_failed_devices):

```bash
mount -o degraded /dev/mapper/left /media/left
```

Umount a luks device

```bash
umount /media/usb
cryptsetup luksClose /dev/mapper/usb
```
